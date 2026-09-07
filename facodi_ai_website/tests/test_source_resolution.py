from hashlib import sha256

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.facodi_ai.services.errors import ValidationError


@tagged("post_install", "-at_install")
class TestWebsiteSourceResolution(TransactionCase):
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
                "name": "FACODI AI Translation Page",
                "type": "qweb",
                "arch": '<t t-name="facodi_ai_website.test_page"><main><p>Hello world</p><a href="/courses">Explore courses</a></main></t>',
                "key": "facodi_ai_website.test_page",
                "website_id": cls.website.id,
            }
        )
        cls.page = cls.env["website.page"].create(
            {
                "view_id": cls.view.id,
                "url": "/facodi-ai-translation-test",
                "website_id": cls.website.id,
            }
        )
        cls.resolver = cls.env["facodi.ai.website.source_resolver"]
        cls.eligibility = cls.env["facodi.ai.website.eligibility"]

    def _sha_for(self, term):
        return sha256(term.encode()).hexdigest()

    def test_resolves_authoritative_default_language_source_by_odoo_sha(self):
        unit = {
            "id": "u1",
            "model": "ir.ui.view",
            "record_id": self.view.id,
            "field": "arch_db",
            "source_sha": self._sha_for("Hello world"),
        }
        resolved = self.resolver.resolve_unit(unit, self.website)
        self.assertEqual(resolved["source_text"], "Hello world")
        self.assertEqual(resolved["source_sha"], unit["source_sha"])
        self.assertEqual(resolved["model"], "ir.ui.view")
        self.assertEqual(resolved["record_id"], self.view.id)
        self.assertEqual(resolved["field"], "arch_db")

    def test_browser_source_text_is_ignored(self):
        unit = {
            "id": "u1",
            "model": "ir.ui.view",
            "record_id": self.view.id,
            "field": "arch_db",
            "source_sha": self._sha_for("Hello world"),
            "source_text": "MALICIOUS BROWSER CONTENT",
        }
        resolved = self.resolver.resolve_unit(unit, self.website)
        self.assertEqual(resolved["source_text"], "Hello world")

    def test_rejects_unknown_or_stale_sha(self):
        unit = {
            "id": "u1",
            "model": "ir.ui.view",
            "record_id": self.view.id,
            "field": "arch_db",
            "source_sha": self._sha_for("stale text"),
        }
        with self.assertRaises(ValidationError):
            self.resolver.resolve_unit(unit, self.website)

    def test_rejects_non_translatable_field(self):
        unit = {
            "id": "u1",
            "model": "ir.ui.view",
            "record_id": self.view.id,
            "field": "key",
            "source_sha": self._sha_for(self.view.key),
        }
        with self.assertRaises(ValidationError):
            self.resolver.resolve_unit(unit, self.website)

    def test_eligibility_accepts_only_current_page_arch(self):
        descriptor = {
            "id": "u1",
            "model": "ir.ui.view",
            "record_id": self.view.id,
            "field": "arch_db",
            "source_sha": self._sha_for("Hello world"),
        }
        self.eligibility.validate_target_language(self.website, "fr_FR")
        self.eligibility.validate_unit(self.website, self.page, descriptor)

    def test_eligibility_rejects_default_language(self):
        with self.assertRaises(ValidationError):
            self.eligibility.validate_target_language(self.website, "en_US")

    def test_eligibility_rejects_language_not_enabled_on_website(self):
        self.env["res.lang"]._activate_lang("de_DE")
        with self.assertRaises(ValidationError):
            self.eligibility.validate_target_language(self.website, "de_DE")

    def test_eligibility_rejects_other_models_and_shared_views(self):
        bad_model = {
            "id": "u1",
            "model": "website.menu",
            "record_id": self.website.menu_id.id,
            "field": "name",
            "source_sha": self._sha_for("Home"),
        }
        with self.assertRaises(ValidationError):
            self.eligibility.validate_unit(self.website, self.page, bad_model)

        shared_view = self.env["ir.ui.view"].create(
            {
                "name": "Shared Header-ish View",
                "type": "qweb",
                "arch": "<div>Shared content</div>",
                "key": "facodi_ai_website.shared_view",
            }
        )
        shared_descriptor = {
            "id": "u2",
            "model": "ir.ui.view",
            "record_id": shared_view.id,
            "field": "arch_db",
            "source_sha": self._sha_for("Shared content"),
        }
        with self.assertRaises(ValidationError):
            self.eligibility.validate_unit(self.website, self.page, shared_descriptor)

    def test_eligibility_rejects_page_from_other_website(self):
        other_website = self.env["website"].create({"name": "Other Website"})
        other_view = self.env["ir.ui.view"].create(
            {
                "name": "Other Website Page",
                "type": "qweb",
                "arch": "<main><p>Other</p></main>",
                "key": "facodi_ai_website.other_page",
                "website_id": other_website.id,
            }
        )
        other_page = self.env["website.page"].create(
            {
                "view_id": other_view.id,
                "url": "/facodi-ai-other",
                "website_id": other_website.id,
            }
        )
        descriptor = {
            "id": "u1",
            "model": "ir.ui.view",
            "record_id": other_view.id,
            "field": "arch_db",
            "source_sha": self._sha_for("Other"),
        }
        with self.assertRaises(ValidationError):
            self.eligibility.validate_unit(self.website, other_page, descriptor)
