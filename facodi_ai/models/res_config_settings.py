from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..services.defaults import get_provider_defaults


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    facodi_ai_enabled = fields.Boolean(
        string="Enable FACODI AI",
        config_parameter="facodi_ai.enabled",
        default=True,
    )
    default_provider_code = fields.Selection(
        [
            ("gemini", "Gemini"),
            ("openai", "OpenAI"),
        ],
        string="Default AI Provider",
        config_parameter="facodi_ai.default_provider",
        default="gemini",
    )
    store_request_payloads = fields.Boolean(
        string="Store AI Request Payloads",
        config_parameter="facodi_ai.store_request_payloads",
        default=False,
        help="Store request and response payloads for debugging. Keep disabled unless needed because payloads may contain Website content.",
    )

    default_openai_connection_id = fields.Many2one(
        "facodi.ai.connection",
        string="Default OpenAI Connection",
        compute="_compute_default_connection_ids",
        inverse="_inverse_default_openai_connection_id",
        groups="base.group_system",
    )
    default_gemini_connection_id = fields.Many2one(
        "facodi.ai.connection",
        string="Default Gemini Connection",
        compute="_compute_default_connection_ids",
        inverse="_inverse_default_gemini_connection_id",
        groups="base.group_system",
    )

    recommended_openai_model = fields.Char(
        string="Recommended OpenAI Model",
        readonly=True,
        default=lambda self: get_provider_defaults("openai").get("model"),
    )
    recommended_gemini_model = fields.Char(
        string="Recommended Gemini Model",
        readonly=True,
        default=lambda self: get_provider_defaults("gemini").get("model"),
    )

    @api.depends_context("uid")
    def _compute_default_connection_ids(self):
        Connection = self.env["facodi.ai.connection"].sudo()
        openai = Connection.search(
            [
                ("provider_id.code", "=", "openai"),
                ("active", "=", True),
                ("is_default", "=", True),
            ],
            limit=1,
        )
        gemini = Connection.search(
            [
                ("provider_id.code", "=", "gemini"),
                ("active", "=", True),
                ("is_default", "=", True),
            ],
            limit=1,
        )
        for settings in self:
            settings.default_openai_connection_id = openai
            settings.default_gemini_connection_id = gemini

    def _set_provider_default_connection(self, provider_code, connection):
        Connection = self.env["facodi.ai.connection"].sudo()
        peers = Connection.search(
            [
                ("provider_id.code", "=", provider_code),
                ("active", "=", True),
                ("is_default", "=", True),
            ]
        )
        if connection:
            connection = connection.sudo().exists()
            if not connection or not connection.active:
                raise ValidationError("The selected AI connection must be active.")
            if connection.provider_id.code != provider_code:
                raise ValidationError(
                    "The selected AI connection belongs to a different provider."
                )
        (peers - connection).with_context(
            facodi_ai_skip_default_enforcement=True
        ).write({"is_default": False})
        if connection and not connection.is_default:
            connection.write({"is_default": True})

    def _inverse_default_openai_connection_id(self):
        for settings in self:
            settings._set_provider_default_connection(
                "openai", settings.default_openai_connection_id
            )

    def _inverse_default_gemini_connection_id(self):
        for settings in self:
            settings._set_provider_default_connection(
                "gemini", settings.default_gemini_connection_id
            )
