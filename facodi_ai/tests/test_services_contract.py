import unittest

from ..services.contracts import (
    TranslationInputUnit,
    TranslationResult,
    TranslationUnitResult,
    validate_translation_result,
)
from ..services.defaults import get_profile_defaults
from ..services.errors import ConfigurationError, ValidationError
from ..services.provider_registry import ProviderAdapterRegistry


class TestServiceContracts(unittest.TestCase):
    def test_translation_result_requires_exact_unique_ids(self):
        units = [
            TranslationInputUnit(id="a", source_sha="sha-a", text="Olá"),
            TranslationInputUnit(id="b", source_sha="sha-b", text="Mundo"),
        ]
        with self.assertRaises(ValidationError):
            validate_translation_result(
                units,
                TranslationResult(
                    units=[
                        TranslationUnitResult(id="a", translated_text="Hello"),
                        TranslationUnitResult(id="a", translated_text="Again"),
                    ]
                ),
            )
        with self.assertRaises(ValidationError):
            validate_translation_result(
                units,
                TranslationResult(units=[TranslationUnitResult(id="a", translated_text="Hello")]),
            )

    def test_protected_tokens_must_be_preserved_exactly(self):
        units = [
            TranslationInputUnit(
                id="a",
                source_sha="sha-a",
                text="Olá {{TAG_1_OPEN}}mundo{{TAG_1_CLOSE}}",
                protected_tokens=["{{TAG_1_OPEN}}", "{{TAG_1_CLOSE}}"],
            )
        ]
        with self.assertRaises(ValidationError):
            validate_translation_result(
                units,
                TranslationResult(
                    units=[
                        TranslationUnitResult(
                            id="a", translated_text="Hello {{TAG_1_OPEN}}world"
                        )
                    ]
                ),
            )

    def test_website_translation_defaults_are_exact(self):
        defaults = get_profile_defaults("website_translation")
        self.assertEqual(defaults["provider"], "gemini")
        self.assertEqual(defaults["timeout"], 60)
        self.assertEqual(defaults["max_tokens"], 8192)
        self.assertEqual(defaults["retries"], 2)
        self.assertTrue(defaults["structured_output"])
        self.assertIsNone(defaults["temperature"])
        defaults["timeout"] = 1
        self.assertEqual(get_profile_defaults("website_translation")["timeout"], 60)

    def test_provider_defaults_are_exact(self):
        defaults = get_profile_defaults("website_translation")
        self.assertEqual(defaults["provider_models"]["openai"], "gpt-5.6-luna")
        self.assertEqual(defaults["provider_models"]["gemini"], "gemini-3.8-flash")

    def test_registry_rejects_duplicate_adapter_keys(self):
        registry = ProviderAdapterRegistry()
        registry.register("fake", object)
        with self.assertRaises(ConfigurationError):
            registry.register("fake", dict)


if __name__ == "__main__":
    unittest.main()
