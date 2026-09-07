from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestWebsiteProfileSetup(TransactionCase):
    def test_install_creates_one_default_website_translation_profile(self):
        prompt = self.env.ref(
            "facodi_ai_website.prompt_website_translation",
            raise_if_not_found=False,
        )
        profile = self.env.ref(
            "facodi_ai_website.profile_website_translation",
            raise_if_not_found=False,
        )

        self.assertTrue(prompt)
        self.assertTrue(profile)
        self.assertEqual(prompt.code, "website_translation")
        self.assertEqual(prompt.capability, "translation")
        self.assertEqual(profile.code, "website_translation")
        self.assertEqual(profile.capability, "translation")
        self.assertEqual(profile.prompt_id, prompt)
        self.assertEqual(
            self.env["facodi.ai.prompt"].search_count(
                [("code", "=", "website_translation")]
            ),
            1,
        )
        self.assertEqual(
            self.env["facodi.ai.profile"].search_count(
                [("code", "=", "website_translation")]
            ),
            1,
        )
        self.assertFalse(profile.provider_id)
        self.assertFalse(profile.connection_id)
        self.assertFalse(profile.model_override)
        self.assertFalse(self.env["facodi.ai.connection"].search([]))

        resolved = self.env["facodi.ai.profile.resolver"]._resolve(profile)
        self.assertEqual(resolved.provider_code, "gemini")
        self.assertEqual(resolved.model_name, "gemini-3.8-flash")
        self.assertEqual(resolved.timeout, 60)
        self.assertEqual(resolved.max_tokens, 8192)
        self.assertEqual(resolved.retries, 2)
        self.assertTrue(resolved.structured_output)
        self.assertIsNone(resolved.temperature)
        self.assertIsNone(resolved.connection_id)

    def test_settings_expose_website_translation_profile_and_effective_values(self):
        Settings = self.env["res.config.settings"]
        expected_fields = (
            "facodi_ai_website_translation_profile_id",
            "facodi_ai_website_translation_provider",
            "facodi_ai_website_translation_model",
            "facodi_ai_website_translation_connection",
        )
        for field_name in expected_fields:
            self.assertIn(field_name, Settings._fields)

        profile = self.env.ref("facodi_ai_website.profile_website_translation")
        settings = Settings.create({})
        self.assertEqual(settings.facodi_ai_website_translation_profile_id, profile)
        self.assertEqual(settings.facodi_ai_website_translation_provider, "gemini")
        self.assertEqual(settings.facodi_ai_website_translation_model, "gemini-3.8-flash")
        self.assertFalse(settings.facodi_ai_website_translation_connection)
