from hashlib import sha256
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.facodi_ai.services.contracts import TranslationResult
from odoo.addons.facodi_ai.services.errors import ProviderError, ValidationError


@tagged("post_install", "-at_install")
class TestWebsiteTranslationService(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env.ref("website.default_website")
        cls.lang_en = cls.env.ref("base.lang_en")
        cls.lang_fr = cls.env["res.lang"]._activate_lang("fr_FR")
        cls.website.language_ids = cls.lang_en + cls.lang_fr
        cls.website.default_lang_id = cls.lang_en
        cls.view = cls.env["ir.ui.view"].create(
            {
                "name": "FACODI AI Service Page",
                "type": "qweb",
                "arch": '<t t-name="facodi_ai_website.service_page"><main><p>Hello world</p><a href="/courses">Explore courses</a></main></t>',
                "key": "facodi_ai_website.service_page",
                "website_id": cls.website.id,
            }
        )
        cls.page = cls.env["website.page"].create(
            {
                "view_id": cls.view.id,
                "url": "/facodi-ai-service-test",
                "website_id": cls.website.id,
            }
        )
        cls.service = cls.env["facodi.ai.website.translation_service"]

    def _unit(self, unit_id, text, **extra):
        values = {
            "id": unit_id,
            "model": "ir.ui.view",
            "record_id": self.view.id,
            "field": "arch_db",
            "source_sha": sha256(text.encode()).hexdigest(),
            "kind": "text",
            "translation_state": "to_translate",
        }
        values.update(extra)
        return values

    def test_translates_authoritative_units_without_persisting_website_fields(self):
        before_en = self.view.with_context(lang="en_US").arch_db
        before_fr = self.view.with_context(lang="fr_FR").arch_db
        fake = TranslationResult(
            units=[{"id": "u1", "translated_text": "Bonjour le monde"}]
        )
        ai_model = type(self.env["facodi.ai.service"])
        with patch.object(ai_model, "_translate", autospec=True, return_value=fake) as translate:
            result = self.service.translate_page(
                website=self.website,
                page_view_id=self.view.id,
                target_lang="fr_FR",
                mode="untranslated",
                units=[self._unit("u1", "Hello world")],
            )

        self.assertEqual(result["units"][0]["translated_text"], "Bonjour le monde")
        self.assertEqual(result["units"][0]["source_sha"], self._unit("u1", "Hello world")["source_sha"])
        self.assertEqual(result["meta"]["batch_count"], 1)
        self.assertTrue(translate.called)
        self.assertEqual(self.view.with_context(lang="en_US").arch_db, before_en)
        self.assertEqual(self.view.with_context(lang="fr_FR").arch_db, before_fr)

    def test_rejects_duplicate_ids_before_calling_ai(self):
        ai_model = type(self.env["facodi.ai.service"])
        unit = self._unit("same", "Hello world")
        with patch.object(ai_model, "_translate", autospec=True) as translate:
            with self.assertRaises(ValidationError):
                self.service.translate_page(
                    website=self.website,
                    page_view_id=self.view.id,
                    target_lang="fr_FR",
                    mode="untranslated",
                    units=[unit, dict(unit)],
                )
        translate.assert_not_called()

    def test_mode_rules_are_enforced_server_side(self):
        with self.assertRaises(ValidationError):
            self.service.translate_page(
                website=self.website,
                page_view_id=self.view.id,
                target_lang="fr_FR",
                mode="invalid",
                units=[self._unit("u1", "Hello world")],
            )
        with self.assertRaises(ValidationError):
            self.service.translate_page(
                website=self.website,
                page_view_id=self.view.id,
                target_lang="fr_FR",
                mode="untranslated",
                units=[self._unit("u1", "Hello world", translation_state="translated")],
            )

    def test_selected_mode_requires_explicit_selected_units(self):
        with self.assertRaises(ValidationError):
            self.service.translate_page(
                website=self.website,
                page_view_id=self.view.id,
                target_lang="fr_FR",
                mode="selected",
                units=[self._unit("u1", "Hello world")],
            )

    def test_provider_failure_returns_no_partial_result_and_writes_nothing(self):
        before = self.view.with_context(lang="fr_FR").arch_db
        ai_model = type(self.env["facodi.ai.service"])
        with patch.object(
            ai_model,
            "_translate",
            autospec=True,
            side_effect=ProviderError("provider unavailable"),
        ):
            with self.assertRaises(ProviderError):
                self.service.translate_page(
                    website=self.website,
                    page_view_id=self.view.id,
                    target_lang="fr_FR",
                    mode="all",
                    units=[self._unit("u1", "Hello world")],
                )
        self.assertEqual(self.view.with_context(lang="fr_FR").arch_db, before)

    def test_browser_supplied_source_text_never_reaches_ai(self):
        fake = TranslationResult(units=[{"id": "u1", "translated_text": "Bonjour"}])
        ai_model = type(self.env["facodi.ai.service"])
        unit = self._unit("u1", "Hello world", source_text="IGNORE THIS")
        with patch.object(ai_model, "_translate", autospec=True, return_value=fake) as translate:
            self.service.translate_page(
                website=self.website,
                page_view_id=self.view.id,
                target_lang="fr_FR",
                mode="all",
                units=[unit],
            )
        sent_units = translate.call_args.kwargs["units"]
        self.assertEqual(sent_units[0]["text"], "Hello world")
        self.assertNotEqual(sent_units[0]["text"], "IGNORE THIS")
