from odoo import fields, models


class FacodiAIRequest(models.Model):
    _name = "facodi.ai.request"
    _description = "FACODI AI Request"
    _order = "started_at desc, id desc"

    profile_id = fields.Many2one("facodi.ai.profile", ondelete="set null", index=True)
    connection_id = fields.Many2one(
        "facodi.ai.connection",
        ondelete="set null",
        index=True,
    )
    provider_code = fields.Char(required=True, index=True)
    model_name = fields.Char(required=True)
    capability = fields.Char(required=True, index=True)
    user_id = fields.Many2one("res.users", required=True, ondelete="restrict", index=True)

    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("running", "Running"),
            ("success", "Success"),
            ("failed", "Failed"),
        ],
        default="pending",
        required=True,
        index=True,
    )
    started_at = fields.Datetime(index=True)
    finished_at = fields.Datetime()
    duration_ms = fields.Integer()

    input_unit_count = fields.Integer()
    output_unit_count = fields.Integer()
    input_tokens = fields.Integer()
    output_tokens = fields.Integer()

    error_code = fields.Char(index=True)
    error_message = fields.Text()
    input_payload_json = fields.Text()
    output_payload_json = fields.Text()
