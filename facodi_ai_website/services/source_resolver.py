from hashlib import sha256

from odoo import models

from odoo.addons.facodi_ai.services.errors import ValidationError


class FacodiAIWebsiteSourceResolver(models.AbstractModel):
    _name = "facodi.ai.website.source_resolver"
    _description = "FACODI AI Website Authoritative Source Resolver"

    def resolve_unit(self, unit, website):
        if not isinstance(unit, dict):
            raise ValidationError("Translation unit must be an object.")

        model_name = unit.get("model")
        record_id = unit.get("record_id")
        field_name = unit.get("field")
        source_sha = unit.get("source_sha")
        unit_id = unit.get("id")
        if not all((unit_id, model_name, record_id, field_name, source_sha)):
            raise ValidationError("Translation unit identity is incomplete.")
        if model_name not in self.env:
            raise ValidationError("Translation unit model is not available.")

        Model = self.env[model_name]
        field = Model._fields.get(field_name)
        if not field or not field.translate:
            raise ValidationError("Translation unit field is not translatable.")

        try:
            record_id = int(record_id)
        except (TypeError, ValueError) as exc:
            raise ValidationError("Translation unit record ID is invalid.") from exc
        record = Model.browse(record_id).exists()
        if not record:
            raise ValidationError("Translation unit record does not exist.")
        try:
            record.check_access("read")
        except Exception as exc:
            raise ValidationError("Translation unit record is not readable.") from exc

        default_lang = website.default_lang_id.code
        if not default_lang:
            raise ValidationError("Website default language is not configured.")
        base_value = record.with_context(lang=default_lang)[field_name] or ""
        if not isinstance(base_value, str):
            raise ValidationError("Translation unit source is not textual.")

        terms_by_sha = {}
        for term in field.get_trans_terms(base_value):
            if not isinstance(term, str):
                continue
            term_sha = sha256(term.encode()).hexdigest()
            terms_by_sha.setdefault(term_sha, term)
        source_text = terms_by_sha.get(source_sha)
        if source_text is None:
            raise ValidationError("Translation unit source is stale or unknown.")

        return {
            "id": str(unit_id),
            "model": model_name,
            "record_id": record.id,
            "field": field_name,
            "source_sha": source_sha,
            "source_text": source_text,
            "kind": unit.get("kind") or "text",
            "attribute": unit.get("attribute"),
            "translation_state": unit.get("translation_state"),
        }
