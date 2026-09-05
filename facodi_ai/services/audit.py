import json
import re

from odoo import api, fields, models


class FacodiAIAudit(models.AbstractModel):
    _name = "facodi.ai.audit"
    _description = "FACODI AI Audit Service"

    @api.model
    def _payload_enabled(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("facodi_ai.store_request_payloads")
            == "1"
        )

    @api.model
    def _sanitize_error(self, message):
        text = str(message or "")
        text = re.sub(
            r"(?i)(api[-_ ]?key|authorization)\s*[:=]\s*\S+",
            r"\1=[redacted]",
            text,
        )
        text = re.sub(r"(?is)\n?traceback\b.*$", "", text)
        return text[:2000]

    @api.model
    def _unit_count(self, payload):
        if not isinstance(payload, dict):
            return 0
        units = payload.get("units")
        return len(units) if isinstance(units, list) else 0

    @api.model
    def _finish_values(self, request):
        finished_at = fields.Datetime.now()
        duration_ms = 0
        if request.started_at:
            duration_ms = max(
                0,
                int((finished_at - request.started_at).total_seconds() * 1000),
            )
        return {
            "finished_at": finished_at,
            "duration_ms": duration_ms,
        }

    @api.model
    def _start(
        self,
        profile,
        connection,
        provider_code,
        model_name,
        capability,
        input_payload,
    ):
        values = {
            "profile_id": profile.id if profile else False,
            "connection_id": connection.id if connection else False,
            "provider_code": provider_code,
            "model_name": model_name,
            "capability": capability,
            "user_id": self.env.user.id,
            "state": "running",
            "started_at": fields.Datetime.now(),
            "input_unit_count": self._unit_count(input_payload),
            "input_payload_json": (
                json.dumps(input_payload, ensure_ascii=False)
                if self._payload_enabled()
                else False
            ),
        }
        return self.env["facodi.ai.request"].sudo().create(values)

    @api.model
    def _success(self, request, output_payload, usage):
        usage = usage or {}
        values = self._finish_values(request)
        values.update(
            {
                "state": "success",
                "output_unit_count": self._unit_count(output_payload),
                "input_tokens": int(usage.get("input_tokens") or 0),
                "output_tokens": int(usage.get("output_tokens") or 0),
                "error_code": False,
                "error_message": False,
                "output_payload_json": (
                    json.dumps(output_payload, ensure_ascii=False)
                    if self._payload_enabled()
                    else False
                ),
            }
        )
        request.sudo().write(values)
        return request

    @api.model
    def _failure(self, request, error_code, message):
        values = self._finish_values(request)
        values.update(
            {
                "state": "failed",
                "error_code": str(error_code or "provider_error")[:128],
                "error_message": self._sanitize_error(message),
                "output_payload_json": False,
            }
        )
        request.sudo().write(values)
        return request
