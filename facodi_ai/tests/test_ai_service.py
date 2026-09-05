from types import SimpleNamespace
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..services.contracts import TranslationResult, TranslationUnitResult
from ..services.errors import (
    AuthenticationError,
    ConfigurationError,
    ProviderError,
    RateLimitError,
    TimeoutError,
)
from ..services.provider_registry import provider_registry


class FakeAdapter:
    def run_structured(self, resolved, api_key, instructions, user_prompt, output_type):
        return (
            output_type(
                units=[TranslationUnitResult(id="u1", translated_text="Hello")]
            ),
            {"input_tokens": 10, "output_tokens": 3},
        )


class RaisingAdapter:
    error = RuntimeError("boom")

    def run_structured(self, resolved, api_key, instructions, user_prompt, output_type):
        raise self.error


class TestAIService(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if "fake_test" not in provider_registry.keys():
            provider_registry.register("fake_test", FakeAdapter)
        if "raising_test" not in provider_registry.keys():
            provider_registry.register("raising_test", RaisingAdapter)

    def _prompt(self):
        return self.env["facodi.ai.prompt"].create(
            {
                "name": "Translation",
                "code": "website_translation",
                "capability": "translation",
                "custom_instructions": "Use FACODI terminology.",
            }
        )

    def _provider(self, code="fake-provider", adapter_key="fake_test"):
        return self.env["facodi.ai.provider"].create(
            {
                "name": code,
                "code": code,
                "adapter_key": adapter_key,
            }
        )

    def _profile(self, provider=False, connection=False):
        values = {
            "name": "Translation",
            "code": "website_translation",
            "capability": "translation",
            "prompt_id": self._prompt().id,
        }
        if provider:
            values.update(
                {
                    "provider_id": provider.id,
                    "model_override": "test-model",
                }
            )
        if connection:
            values["connection_id"] = connection.id
        return self.env["facodi.ai.profile"].create(values)

    def _connection(self, provider, key="test-secret"):
        return self.env["facodi.ai.connection"].create(
            {
                "name": "Test Connection",
                "provider_id": provider.id,
                "api_key": key,
                "is_default": True,
            }
        )

    def _translate(self, profile):
        return self.env["facodi.ai.service"]._translate(
            profile=profile,
            units=[
                {
                    "id": "u1",
                    "source_sha": "abc",
                    "text": "Olá",
                    "protected_tokens": [],
                }
            ],
            source_lang="pt_PT",
            target_lang="en_US",
            context={"website": "FACODI"},
        )

    def test_missing_connection_fails_before_provider_call(self):
        profile = self._profile()
        with self.assertRaises(ConfigurationError):
            self._translate(profile)
        self.assertFalse(self.env["facodi.ai.request"].search([]))

    def test_successful_translation_returns_contract_and_audits_metadata(self):
        provider = self._provider()
        connection = self._connection(provider)
        profile = self._profile(provider=provider, connection=connection)

        result = self._translate(profile)

        self.assertIsInstance(result, TranslationResult)
        self.assertEqual(result.units[0].translated_text, "Hello")
        request = self.env["facodi.ai.request"].search([], limit=1)
        self.assertEqual(request.state, "success")
        self.assertEqual(request.provider_code, provider.code)
        self.assertEqual(request.connection_id, connection)
        self.assertEqual(request.input_tokens, 10)
        self.assertEqual(request.output_tokens, 3)
        self.assertFalse(request.input_payload_json)
        self.assertFalse(request.output_payload_json)

    def test_disabled_ai_fails_before_provider_call(self):
        provider = self._provider()
        connection = self._connection(provider)
        profile = self._profile(provider=provider, connection=connection)
        self.env["ir.config_parameter"].sudo().set_param("facodi_ai.enabled", "0")
        with self.assertRaises(ConfigurationError):
            self._translate(profile)

    def test_missing_api_key_fails_before_audit_provider_call(self):
        provider = self._provider()
        connection = self._connection(provider, key=False)
        profile = self._profile(provider=provider, connection=connection)
        with self.assertRaises(ConfigurationError):
            self._translate(profile)

    def test_provider_errors_are_normalized_and_audited(self):
        provider = self._provider(code="raising", adapter_key="raising_test")
        connection = self._connection(provider)
        profile = self._profile(provider=provider, connection=connection)

        cases = [
            (RuntimeError("authentication invalid api key"), AuthenticationError),
            (RuntimeError("HTTP 429 rate limit exceeded"), RateLimitError),
            (RuntimeError("request timed out"), TimeoutError),
            (RuntimeError("unclassified provider failure"), ProviderError),
        ]
        for error, expected in cases:
            RaisingAdapter.error = error
            try:
                self._translate(profile)
            except expected:
                pass
            except Exception as unexpected:
                self.fail(
                    f"Expected {expected.__name__}, got {type(unexpected).__name__}: {unexpected}"
                )
            else:
                self.fail(f"Expected {expected.__name__} to be raised")
            request = self.env["facodi.ai.request"].search([], order="id desc", limit=1)
            self.assertEqual(request.state, "failed")
            self.assertEqual(request.error_code, expected.code)

    def test_custom_prompt_instructions_are_appended(self):
        captured = {}

        class CapturingAdapter(FakeAdapter):
            def run_structured(self, resolved, api_key, instructions, user_prompt, output_type):
                captured["instructions"] = instructions
                captured["user_prompt"] = user_prompt
                return super().run_structured(
                    resolved, api_key, instructions, user_prompt, output_type
                )

        if "capturing_test" not in provider_registry.keys():
            provider_registry.register("capturing_test", CapturingAdapter)
        provider = self._provider(code="capturing", adapter_key="capturing_test")
        connection = self._connection(provider)
        profile = self._profile(provider=provider, connection=connection)
        self._translate(profile)
        self.assertIn("Use FACODI terminology.", captured["instructions"])
        self.assertIn('"source_lang": "pt_PT"', captured["user_prompt"])
        self.assertIn('"target_lang": "en_US"', captured["user_prompt"])


class TestProviderAdapters(TransactionCase):
    def setUp(self):
        super().setUp()
        self.resolved = SimpleNamespace(
            model_name="test-model",
            timeout=30,
            max_tokens=512,
            retries=1,
            temperature=None,
        )
        self.output = TranslationResult(
            units=[TranslationUnitResult(id="u1", translated_text="Hello")]
        )

    @patch("odoo.addons.facodi_ai.services.adapters.openai.Agent.run_sync")
    def test_openai_adapter_returns_facodi_contract(self, run_sync):
        from ..services.adapters.openai import OpenAIAdapter

        run_sync.return_value = SimpleNamespace(
            output=self.output,
            usage=lambda: SimpleNamespace(input_tokens=8, output_tokens=2),
        )
        output, usage = OpenAIAdapter().run_structured(
            self.resolved,
            "fake-key",
            "instructions",
            "prompt",
            TranslationResult,
        )
        self.assertEqual(output, self.output)
        self.assertEqual(usage, {"input_tokens": 8, "output_tokens": 2})

    @patch("odoo.addons.facodi_ai.services.adapters.gemini.Agent.run_sync")
    def test_gemini_adapter_returns_facodi_contract(self, run_sync):
        from ..services.adapters.gemini import GeminiAdapter

        run_sync.return_value = SimpleNamespace(
            output=self.output,
            usage=lambda: SimpleNamespace(input_tokens=7, output_tokens=3),
        )
        output, usage = GeminiAdapter().run_structured(
            self.resolved,
            "fake-key",
            "instructions",
            "prompt",
            TranslationResult,
        )
        self.assertEqual(output, self.output)
        self.assertEqual(usage, {"input_tokens": 7, "output_tokens": 3})
