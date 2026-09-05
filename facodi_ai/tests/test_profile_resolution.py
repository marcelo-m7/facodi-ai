from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase

from ..services.defaults import get_provider_defaults
from ..services.errors import ConfigurationError


class TestProfileResolution(TransactionCase):
    def setUp(self):
        super().setUp()
        self.gemini = self.env.ref("facodi_ai.provider_gemini")
        self.openai = self.env.ref("facodi_ai.provider_openai")
        self.prompt = self.env["facodi.ai.prompt"].create(
            {
                "name": "Website Translation",
                "code": "website_translation",
                "capability": "translation",
            }
        )

    def _profile(self, **values):
        payload = {
            "name": "Website Translation",
            "code": "website_translation",
            "capability": "translation",
            "prompt_id": self.prompt.id,
        }
        payload.update(values)
        return self.env["facodi.ai.profile"].create(payload)

    def test_provider_defaults_are_available_without_mutation(self):
        defaults = get_provider_defaults("gemini")
        self.assertEqual(defaults["model"], "gemini-3.8-flash")
        defaults["model"] = "changed"
        self.assertEqual(
            get_provider_defaults("gemini")["model"],
            "gemini-3.8-flash",
        )

    def test_code_defaults_are_effective_without_being_stored(self):
        profile = self._profile()
        resolved = self.env["facodi.ai.profile.resolver"]._resolve(profile)
        self.assertEqual(resolved.provider_code, "gemini")
        self.assertEqual(resolved.model_name, "gemini-3.8-flash")
        self.assertEqual(resolved.timeout, 60)
        self.assertEqual(resolved.max_tokens, 8192)
        self.assertEqual(resolved.retries, 2)
        self.assertTrue(resolved.structured_output)
        self.assertIsNone(resolved.temperature)
        self.assertFalse(profile.model_override)
        self.assertIsNone(resolved.connection_id)

    def test_explicit_connection_changes_provider_and_model(self):
        connection = self.env["facodi.ai.connection"].create(
            {
                "name": "OpenAI",
                "provider_id": self.openai.id,
                "is_default": True,
            }
        )
        profile = self._profile(connection_id=connection.id)
        resolved = self.env["facodi.ai.profile.resolver"]._resolve(profile)
        self.assertEqual(resolved.provider_code, "openai")
        self.assertEqual(resolved.connection_id, connection.id)
        self.assertEqual(resolved.model_name, "gpt-5.6-luna")

    def test_default_connection_is_preferred_for_effective_provider(self):
        self.env["facodi.ai.connection"].create(
            {"name": "Gemini Other", "provider_id": self.gemini.id}
        )
        expected = self.env["facodi.ai.connection"].create(
            {
                "name": "Gemini Default",
                "provider_id": self.gemini.id,
                "is_default": True,
            }
        )
        resolved = self.env["facodi.ai.profile.resolver"]._resolve(self._profile())
        self.assertEqual(resolved.connection_id, expected.id)

    def test_only_active_connection_is_selected_when_there_is_no_default(self):
        expected = self.env["facodi.ai.connection"].create(
            {"name": "Only Gemini", "provider_id": self.gemini.id}
        )
        resolved = self.env["facodi.ai.profile.resolver"]._resolve(self._profile())
        self.assertEqual(resolved.connection_id, expected.id)

    def test_ambiguous_connections_leave_connection_unresolved(self):
        self.env["facodi.ai.connection"].create(
            {"name": "Gemini A", "provider_id": self.gemini.id}
        )
        self.env["facodi.ai.connection"].create(
            {"name": "Gemini B", "provider_id": self.gemini.id}
        )
        resolved = self.env["facodi.ai.profile.resolver"]._resolve(self._profile())
        self.assertIsNone(resolved.connection_id)

    def test_global_provider_is_used_only_when_feature_has_no_provider_default(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "facodi_ai.default_provider",
            "openai",
        )
        prompt = self.env["facodi.ai.prompt"].create(
            {
                "name": "Custom Capability",
                "code": "custom_capability",
                "capability": "generation",
            }
        )
        profile = self.env["facodi.ai.profile"].create(
            {
                "name": "Custom Capability",
                "code": "custom_capability",
                "capability": "generation",
                "prompt_id": prompt.id,
            }
        )
        resolved = self.env["facodi.ai.profile.resolver"]._resolve(profile)
        self.assertEqual(resolved.provider_code, "openai")

    def test_missing_provider_configuration_raises_normalized_error(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "facodi_ai.default_provider",
            False,
        )
        prompt = self.env["facodi.ai.prompt"].create(
            {
                "name": "No Provider",
                "code": "no_provider",
                "capability": "generation",
            }
        )
        profile = self.env["facodi.ai.profile"].create(
            {
                "name": "No Provider",
                "code": "no_provider",
                "capability": "generation",
                "prompt_id": prompt.id,
            }
        )
        with self.assertRaises(ConfigurationError):
            self.env["facodi.ai.profile.resolver"]._resolve(profile)

    def test_explicit_runtime_overrides_win_even_for_zero_temperature(self):
        profile = self._profile(
            model_override="gemini-custom",
            temperature_overridden=True,
            temperature_override=0.0,
            timeout_override=30,
            max_tokens_override=1024,
            retries_override=4,
            structured_output_override="disabled",
        )
        resolved = self.env["facodi.ai.profile.resolver"]._resolve(profile)
        self.assertEqual(resolved.model_name, "gemini-custom")
        self.assertEqual(resolved.temperature, 0.0)
        self.assertEqual(resolved.timeout, 30)
        self.assertEqual(resolved.max_tokens, 1024)
        self.assertEqual(resolved.retries, 4)
        self.assertFalse(resolved.structured_output)

    def test_provider_and_connection_must_match(self):
        connection = self.env["facodi.ai.connection"].create(
            {"name": "OpenAI", "provider_id": self.openai.id}
        )
        with self.assertRaises(ValidationError):
            self._profile(
                provider_id=self.gemini.id,
                connection_id=connection.id,
            )

    def test_fallback_chain_cannot_cycle(self):
        first = self._profile(name="First")
        second = self._profile(name="Second", fallback_profile_id=first.id)
        with self.assertRaises(ValidationError):
            first.write({"fallback_profile_id": second.id})
