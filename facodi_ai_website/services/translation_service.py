from odoo import api, models

from odoo.addons.facodi_ai.services.errors import ValidationError


MAX_UNITS = 500
BATCH_CHARACTER_BUDGET = 6000
ALLOWED_MODES = {"untranslated", "all", "selected"}


class FacodiAIWebsiteTranslationService(models.AbstractModel):
    _name = "facodi.ai.website.translation_service"
    _description = "FACODI AI Website Translation Service"

    @api.model
    def translate_page(self, *, website, page_view_id, target_lang, mode, units):
        if mode not in ALLOWED_MODES:
            raise ValidationError("Unsupported Website translation mode.")
        if not isinstance(units, list) or not units:
            raise ValidationError("At least one Website translation unit is required.")
        if len(units) > MAX_UNITS:
            raise ValidationError("Too many Website translation units were requested at once.")

        unit_ids = [str(unit.get("id")) for unit in units if isinstance(unit, dict)]
        if len(unit_ids) != len(units) or any(not unit_id for unit_id in unit_ids):
            raise ValidationError("Every Website translation unit must have an ID.")
        if len(unit_ids) != len(set(unit_ids)):
            raise ValidationError("Website translation unit IDs must be unique.")

        try:
            page_view_id = int(page_view_id)
        except (TypeError, ValueError) as exc:
            raise ValidationError("Website page view ID is invalid.") from exc
        page = self.env["website.page"].search(
            [
                ("view_id", "=", page_view_id),
                ("website_id", "=", website.id),
            ],
            limit=1,
        )
        eligibility = self.env["facodi.ai.website.eligibility"]
        page = eligibility.validate_page(website, page)
        target_language = eligibility.resolve_target_language(website, target_lang)

        resolver = self.env["facodi.ai.website.source_resolver"]
        markup = self.env["facodi.ai.website.markup"]
        prepared = []
        for unit in units:
            self._validate_mode_unit(mode, unit)
            eligibility.validate_unit(website, page, unit)
            resolved = resolver.resolve_unit(unit, website)
            protected = markup.protect(resolved["source_text"])
            prepared.append(
                {
                    "descriptor": resolved,
                    "protected": protected,
                    "ai_unit": {
                        "id": resolved["id"],
                        "source_sha": resolved["source_sha"],
                        "text": protected["text"],
                        "protected_tokens": protected["protected_tokens"],
                    },
                }
            )

        batches = self._build_batches(prepared)
        profile = self.env.ref("facodi_ai_website.profile_website_translation")
        ai_service = self.env["facodi.ai.service"]
        translated_by_id = {}
        for batch in batches:
            result = ai_service._translate(
                profile=profile,
                units=[entry["ai_unit"] for entry in batch],
                source_lang=website.default_lang_id.code,
                target_lang=target_language.code,
                context={
                    "website_id": website.id,
                    "page_id": page.id,
                    "page_view_id": page.view_id.id,
                    "mode": mode,
                },
            )
            for translated in result.units:
                if translated.id in translated_by_id:
                    raise ValidationError("AI returned a duplicate Website translation unit.")
                translated_by_id[translated.id] = translated.translated_text

        expected_ids = {entry["descriptor"]["id"] for entry in prepared}
        if set(translated_by_id) != expected_ids:
            raise ValidationError("AI response does not contain every Website translation unit.")

        response_units = []
        for entry in prepared:
            descriptor = entry["descriptor"]
            translated_text = markup.reconstruct(
                entry["protected"], translated_by_id[descriptor["id"]]
            )
            response_units.append(
                {
                    "id": descriptor["id"],
                    "source_sha": descriptor["source_sha"],
                    "translated_text": translated_text,
                }
            )

        runtime = self.env["facodi.ai.profile.resolver"]._resolve(profile)
        return {
            "units": response_units,
            "meta": {
                "provider": runtime.provider_code,
                "model": runtime.model_name,
                "batch_count": len(batches),
                "source_lang": website.default_lang_id.code,
                "target_lang": target_language.code,
                "mode": mode,
            },
        }

    @api.model
    def _validate_mode_unit(self, mode, unit):
        if not isinstance(unit, dict):
            raise ValidationError("Website translation unit must be an object.")
        if mode == "untranslated" and unit.get("translation_state") != "to_translate":
            raise ValidationError("Untranslated mode only accepts untranslated Odoo units.")
        if mode == "selected" and unit.get("selected") is not True:
            raise ValidationError("Selected mode requires explicitly selected Odoo units.")

    @api.model
    def _build_batches(self, prepared):
        batches = []
        current = []
        current_size = 0
        for entry in prepared:
            size = len(entry["ai_unit"]["text"])
            if current and current_size + size > BATCH_CHARACTER_BUDGET:
                batches.append(current)
                current = []
                current_size = 0
            current.append(entry)
            current_size += size
        if current:
            batches.append(current)
        return batches
