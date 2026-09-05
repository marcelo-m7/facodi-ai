from odoo.tests.common import TransactionCase


class TestRequestAudit(TransactionCase):
    def _start(self, **overrides):
        values = {
            "profile": False,
            "connection": False,
            "provider_code": "gemini",
            "model_name": "gemini-3.8-flash",
            "capability": "translation",
            "input_payload": {
                "units": [
                    {"id": "u1", "text": "private page content"},
                    {"id": "u2", "text": "second unit"},
                ]
            },
        }
        values.update(overrides)
        return self.env["facodi.ai.audit"]._start(**values)

    def test_payload_is_not_stored_by_default(self):
        request = self._start()
        self.assertFalse(request.input_payload_json)
        self.assertEqual(request.input_unit_count, 2)
        self.env["facodi.ai.audit"]._success(
            request,
            output_payload={"units": [{"id": "u1"}, {"id": "u2"}]},
            usage={"input_tokens": 20, "output_tokens": 8},
        )
        self.assertFalse(request.output_payload_json)
        self.assertEqual(request.state, "success")
        self.assertEqual(request.output_unit_count, 2)
        self.assertEqual(request.input_tokens, 20)
        self.assertEqual(request.output_tokens, 8)
        self.assertTrue(request.finished_at)
        self.assertGreaterEqual(request.duration_ms, 0)

    def test_payload_can_be_explicitly_enabled(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "facodi_ai.store_request_payloads",
            "1",
        )
        request = self._start(
            provider_code="openai",
            model_name="gpt-5.6-luna",
            input_payload={"text": "content"},
        )
        self.assertIn("content", request.input_payload_json)
        self.env["facodi.ai.audit"]._success(
            request,
            output_payload={"text": "translated"},
            usage={},
        )
        self.assertIn("translated", request.output_payload_json)

    def test_failure_is_normalized_and_never_stores_traceback_or_key(self):
        request = self._start()
        self.env["facodi.ai.audit"]._failure(
            request,
            error_code="authentication_error",
            message="Authorization: sk-secret-value\nTraceback (most recent call last): hidden",
        )
        self.assertEqual(request.state, "failed")
        self.assertEqual(request.error_code, "authentication_error")
        self.assertNotIn("sk-secret-value", request.error_message)
        self.assertNotIn("Traceback", request.error_message)
        self.assertTrue(request.finished_at)

    def test_request_is_attributed_to_current_user(self):
        request = self._start()
        self.assertEqual(request.user_id, self.env.user)
        self.assertEqual(request.state, "running")
        self.assertTrue(request.started_at)

    def test_payload_switch_accepts_only_explicit_one(self):
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("facodi_ai.store_request_payloads", "true")
        self.assertFalse(self.env["facodi.ai.audit"]._payload_enabled())
        params.set_param("facodi_ai.store_request_payloads", "1")
        self.assertTrue(self.env["facodi.ai.audit"]._payload_enabled())
