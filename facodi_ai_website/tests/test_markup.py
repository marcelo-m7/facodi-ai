from odoo.tests.common import TransactionCase, tagged

from odoo.addons.facodi_ai.services.errors import ValidationError


@tagged("post_install", "-at_install")
class TestWebsiteMarkupProtection(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.markup = cls.env["facodi.ai.website.markup"]

    def test_protects_markup_as_opaque_tokens_and_restores_exact_tags(self):
        source = '  Read <a href="/courses" class="btn">our <strong>courses</strong></a>.  '
        protected = self.markup.protect(source)

        self.assertNotIn('<a href="/courses"', protected["text"])
        self.assertNotIn("<strong>", protected["text"])
        self.assertTrue(protected["protected_tokens"])

        translated = protected["text"].replace("Read ", "Leia ").replace("our ", "os nossos ").replace("courses", "cursos")
        restored = self.markup.reconstruct(protected, translated)

        self.assertIn('<a href="/courses" class="btn">', restored)
        self.assertIn("<strong>cursos</strong>", restored)
        self.assertTrue(restored.startswith("  "))
        self.assertTrue(restored.endswith("  "))

    def test_rejects_missing_duplicate_or_reordered_tokens(self):
        protected = self.markup.protect("A <strong>bold</strong> value")
        tokens = protected["protected_tokens"]

        with self.assertRaises(ValidationError):
            self.markup.reconstruct(protected, protected["text"].replace(tokens[0], ""))

        with self.assertRaises(ValidationError):
            self.markup.reconstruct(protected, protected["text"] + tokens[0])

        reordered = protected["text"]
        for index, token in enumerate(tokens):
            reordered = reordered.replace(token, f"__TMP_{index}__")
        reordered = reordered.replace("__TMP_0__", tokens[-1]).replace(
            f"__TMP_{len(tokens) - 1}__", tokens[0]
        )
        with self.assertRaises(ValidationError):
            self.markup.reconstruct(protected, reordered)

    def test_rejects_model_generated_raw_markup(self):
        protected = self.markup.protect("Safe text")
        with self.assertRaises(ValidationError):
            self.markup.reconstruct(protected, "Unsafe <script>alert(1)</script>")

    def test_rejects_leading_or_trailing_whitespace_changes(self):
        protected = self.markup.protect("  Hello  ")
        with self.assertRaises(ValidationError):
            self.markup.reconstruct(protected, protected["text"].strip())

    def test_plain_text_round_trip(self):
        protected = self.markup.protect("Hello world")
        self.assertEqual(protected["protected_tokens"], [])
        self.assertEqual(self.markup.reconstruct(protected, "Bonjour le monde"), "Bonjour le monde")
