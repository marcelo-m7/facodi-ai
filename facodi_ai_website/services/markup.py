import re

from odoo import models

from odoo.addons.facodi_ai.services.errors import ValidationError


_TAG_RE = re.compile(r"<[^>]+>")
_TOKEN_RE = re.compile(r"\{\{FACODI_TAG_\d{4}\}\}")
_LEADING_WS_RE = re.compile(r"^\s*")
_TRAILING_WS_RE = re.compile(r"\s*$")


class FacodiAIWebsiteMarkup(models.AbstractModel):
    _name = "facodi.ai.website.markup"
    _description = "FACODI AI Website Markup Protection"

    def protect(self, source_text):
        if not isinstance(source_text, str):
            raise ValidationError("Translation source must be text.")

        replacements = []

        def replace_tag(match):
            token = f"{{{{FACODI_TAG_{len(replacements):04d}}}}}"
            replacements.append((token, match.group(0)))
            return token

        protected_text = _TAG_RE.sub(replace_tag, source_text)
        return {
            "text": protected_text,
            "protected_tokens": [token for token, _tag in replacements],
            "replacements": replacements,
            "leading_ws": _LEADING_WS_RE.match(source_text).group(0),
            "trailing_ws": _TRAILING_WS_RE.search(source_text).group(0),
        }

    def reconstruct(self, protected, translated_text):
        if not isinstance(protected, dict) or not isinstance(translated_text, str):
            raise ValidationError("Translated markup payload is invalid.")

        tokens = list(protected.get("protected_tokens") or [])
        if _TOKEN_RE.findall(translated_text) != tokens:
            raise ValidationError("Protected markup tokens were not preserved in order.")
        if "<" in translated_text or ">" in translated_text:
            raise ValidationError("AI translation introduced untrusted markup.")

        expected_leading = protected.get("leading_ws", "")
        expected_trailing = protected.get("trailing_ws", "")
        if _LEADING_WS_RE.match(translated_text).group(0) != expected_leading:
            raise ValidationError("Leading whitespace was not preserved.")
        if _TRAILING_WS_RE.search(translated_text).group(0) != expected_trailing:
            raise ValidationError("Trailing whitespace was not preserved.")

        restored = translated_text
        replacements = list(protected.get("replacements") or [])
        if [token for token, _tag in replacements] != tokens:
            raise ValidationError("Protected markup metadata is inconsistent.")
        for token, original_tag in replacements:
            restored = restored.replace(token, original_tag)
        return restored
