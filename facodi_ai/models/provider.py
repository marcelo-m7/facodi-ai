from odoo import fields, models


class FacodiAIProvider(models.Model):
    _name = "facodi.ai.provider"
    _description = "FACODI AI Provider"
    _order = "sequence, name"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    adapter_key = fields.Char(required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "Provider code must be unique.",
    )
