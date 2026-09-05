from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .prompt import AI_CAPABILITIES


class FacodiAIProfile(models.Model):
    _name = "facodi.ai.profile"
    _description = "FACODI AI Profile"
    _order = "name, id"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    capability = fields.Selection(AI_CAPABILITIES, required=True, index=True)
    active = fields.Boolean(default=True)

    provider_id = fields.Many2one(
        "facodi.ai.provider",
        ondelete="restrict",
    )
    connection_id = fields.Many2one(
        "facodi.ai.connection",
        ondelete="restrict",
    )
    prompt_id = fields.Many2one(
        "facodi.ai.prompt",
        ondelete="restrict",
    )
    fallback_profile_id = fields.Many2one(
        "facodi.ai.profile",
        ondelete="restrict",
    )

    model_override = fields.Char()
    temperature_overridden = fields.Boolean(default=False)
    temperature_override = fields.Float()
    timeout_override = fields.Integer()
    max_tokens_override = fields.Integer()
    retries_override = fields.Integer()
    structured_output_override = fields.Selection(
        [
            ("default", "Use Default"),
            ("enabled", "Enabled"),
            ("disabled", "Disabled"),
        ],
        default="default",
        required=True,
    )

    @api.constrains("provider_id", "connection_id")
    def _check_provider_connection(self):
        for record in self:
            if (
                record.provider_id
                and record.connection_id
                and record.connection_id.provider_id != record.provider_id
            ):
                raise ValidationError(
                    "The selected AI connection must belong to the selected provider."
                )

    @api.constrains("fallback_profile_id")
    def _check_fallback_cycle(self):
        for record in self:
            seen = {record.id} if record.id else set()
            current = record.fallback_profile_id
            while current:
                if current.id in seen:
                    raise ValidationError("AI profile fallback chains cannot contain cycles.")
                seen.add(current.id)
                current = current.fallback_profile_id
