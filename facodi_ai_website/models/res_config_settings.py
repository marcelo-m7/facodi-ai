from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    facodi_ai_website_translation_profile_id = fields.Many2one(
        "facodi.ai.profile",
        string="Website Translation Profile",
        compute="_compute_facodi_ai_website_translation_effective_values",
        readonly=True,
    )
    facodi_ai_website_translation_provider = fields.Char(
        string="Effective Provider",
        compute="_compute_facodi_ai_website_translation_effective_values",
        readonly=True,
    )
    facodi_ai_website_translation_model = fields.Char(
        string="Effective Model",
        compute="_compute_facodi_ai_website_translation_effective_values",
        readonly=True,
    )
    facodi_ai_website_translation_connection = fields.Many2one(
        "facodi.ai.connection",
        string="Effective Connection",
        compute="_compute_facodi_ai_website_translation_effective_values",
        readonly=True,
    )

    @api.depends_context("uid")
    def _compute_facodi_ai_website_translation_effective_values(self):
        profile = self.env.ref(
            "facodi_ai_website.profile_website_translation",
            raise_if_not_found=False,
        )
        resolved = (
            self.env["facodi.ai.profile.resolver"]._resolve(profile)
            if profile
            else None
        )
        connection = (
            self.env["facodi.ai.connection"].browse(resolved.connection_id).exists()
            if resolved and resolved.connection_id
            else self.env["facodi.ai.connection"]
        )
        for settings in self:
            settings.facodi_ai_website_translation_profile_id = profile
            settings.facodi_ai_website_translation_provider = (
                resolved.provider_code if resolved else False
            )
            settings.facodi_ai_website_translation_model = (
                resolved.model_name if resolved else False
            )
            settings.facodi_ai_website_translation_connection = connection
