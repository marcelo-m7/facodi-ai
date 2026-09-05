import uuid

from odoo import api, fields, models
from odoo.exceptions import ValidationError

# Importing the service registers the private AbstractModel in Odoo's registry.
from ..services import secret_store  # noqa: F401


class FacodiAIConnection(models.Model):
    _name = "facodi.ai.connection"
    _description = "FACODI AI Connection"
    _order = "sequence, name"

    name = fields.Char(required=True)
    provider_id = fields.Many2one(
        "facodi.ai.provider",
        required=True,
        ondelete="restrict",
        index=True,
    )
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    is_default = fields.Boolean(default=False, copy=False)

    credential_uuid = fields.Char(
        required=True,
        readonly=True,
        copy=False,
        index=True,
    )
    api_key = fields.Char(
        string="API Key",
        compute="_compute_api_key",
        inverse="_inverse_api_key",
        groups="base.group_system",
        copy=False,
    )
    api_key_configured = fields.Boolean(
        string="API Key Configured",
        compute="_compute_api_key_configured",
    )

    base_url = fields.Char()
    organization = fields.Char()
    project = fields.Char()

    last_tested_at = fields.Datetime(readonly=True, copy=False)
    last_test_status = fields.Selection(
        [
            ("never", "Never Tested"),
            ("success", "Success"),
            ("failed", "Failed"),
        ],
        default="never",
        readonly=True,
        copy=False,
    )
    last_test_message = fields.Text(readonly=True, copy=False)

    _credential_uuid_unique = models.Constraint(
        "UNIQUE(credential_uuid)",
        "Connection credential identifier must be unique.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals = []
        pending_api_keys = []
        for values in vals_list:
            values = dict(values)
            values["credential_uuid"] = uuid.uuid4().hex
            pending_api_keys.append(values.pop("api_key", False))
            prepared_vals.append(values)

        records = super().create(prepared_vals)
        secret_store_model = self.env["facodi.ai.secret.store"]
        for record, api_key in zip(records, pending_api_keys):
            if api_key:
                secret_store_model._set_connection_api_key(record, api_key)
                record.invalidate_recordset(["api_key_configured"])
            if record.active and record.is_default:
                record._enforce_single_default()
        return records

    def write(self, vals):
        if "credential_uuid" in vals:
            requested = vals["credential_uuid"]
            if any(record.credential_uuid != requested for record in self):
                raise ValidationError("The credential identifier cannot be changed.")

        result = super().write(vals)
        if (
            not self.env.context.get("facodi_ai_skip_default_enforcement")
            and {"provider_id", "active", "is_default"}.intersection(vals)
        ):
            for record in self:
                if record.active and record.is_default:
                    record._enforce_single_default()
        return result

    def unlink(self):
        store = self.env["facodi.ai.secret.store"]
        for record in self:
            store._delete_connection_api_key(record)
        return super().unlink()

    def _compute_api_key(self):
        for record in self:
            record.api_key = False

    def _inverse_api_key(self):
        store = self.env["facodi.ai.secret.store"]
        for record in self:
            if record.api_key:
                store._set_connection_api_key(record, record.api_key)
                record.invalidate_recordset(["api_key_configured"])

    @api.depends("credential_uuid")
    def _compute_api_key_configured(self):
        store = self.env["facodi.ai.secret.store"]
        for record in self:
            record.api_key_configured = bool(
                record.credential_uuid and store._has_connection_api_key(record)
            )

    def _enforce_single_default(self):
        for record in self:
            if not record.active or not record.is_default:
                continue
            peers = self.search(
                [
                    ("id", "!=", record.id),
                    ("provider_id", "=", record.provider_id.id),
                    ("active", "=", True),
                    ("is_default", "=", True),
                ]
            )
            if peers:
                peers.with_context(facodi_ai_skip_default_enforcement=True).write(
                    {"is_default": False}
                )
