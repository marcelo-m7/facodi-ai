from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    facodi_ai_learning_profile_id = fields.Many2one(
        "facodi.ai.profile",
        string="Learning Analysis Profile",
        config_parameter="facodi_ai.learning_profile_id",
        domain="[('active', '=', True), ('capability', 'in', ('classification', 'extraction', 'generation'))]",
        groups="base.group_system",
    )
