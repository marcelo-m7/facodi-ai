from odoo import fields, models


AI_CAPABILITIES = [
    ("translation", "Translation"),
    ("generation", "Generation"),
    ("summarization", "Summarization"),
    ("classification", "Classification"),
    ("extraction", "Extraction"),
]


class FacodiAIPrompt(models.Model):
    _name = "facodi.ai.prompt"
    _description = "FACODI AI Prompt"
    _order = "code, version desc, id desc"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    capability = fields.Selection(AI_CAPABILITIES, required=True, index=True)
    active = fields.Boolean(default=True)
    custom_instructions = fields.Text()
    version = fields.Integer(default=1, required=True)
