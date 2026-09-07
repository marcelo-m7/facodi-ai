from odoo import models

from odoo.addons.facodi_ai.services.errors import ValidationError


class FacodiAIWebsiteEligibility(models.AbstractModel):
    _name = "facodi.ai.website.eligibility"
    _description = "FACODI AI Website Translation Eligibility"

    def resolve_target_language(self, website, target_lang):
        if not target_lang:
            raise ValidationError("Target language is required.")
        language = website.language_ids.filtered(
            lambda lang: lang.code == target_lang or lang.url_code == target_lang
        )[:1]
        if not language:
            raise ValidationError("Target language is not enabled on this Website.")
        if language == website.default_lang_id:
            raise ValidationError("The Website default language cannot be a translation target.")
        return language

    def validate_target_language(self, website, target_lang):
        return self.resolve_target_language(website, target_lang)

    def validate_page(self, website, page):
        page = page.exists()
        if not page:
            raise ValidationError("Website page does not exist.")
        if not page.website_id or page.website_id != website:
            raise ValidationError("Website page is outside the current Website scope.")
        return page

    def validate_unit(self, website, page, unit):
        page = self.validate_page(website, page)
        if not isinstance(unit, dict):
            raise ValidationError("Translation unit must be an object.")
        if unit.get("model") != "ir.ui.view":
            raise ValidationError("Only local Website page view content is eligible for V1 translation.")
        if unit.get("field") != "arch_db":
            raise ValidationError("Only the local Website page architecture is eligible for V1 translation.")
        try:
            record_id = int(unit.get("record_id"))
        except (TypeError, ValueError) as exc:
            raise ValidationError("Translation unit record ID is invalid.") from exc
        if record_id != page.view_id.id:
            raise ValidationError("Translation unit is not owned by the current Website page.")
        if page.view_id.website_id != website:
            raise ValidationError("Translation unit view is not Website-local.")
        return True
