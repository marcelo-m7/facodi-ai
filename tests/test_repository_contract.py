import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_manifest(addon):
    path = ROOT / addon / "__manifest__.py"
    return ast.literal_eval(path.read_text())


class RepositoryContractTest(unittest.TestCase):
    def test_addon_boundaries(self):
        core = load_manifest("facodi_ai")
        website = load_manifest("facodi_ai_website")
        self.assertNotIn("website", core["depends"])
        self.assertNotIn("website_slides", core["depends"])
        self.assertEqual(website["depends"], ["website", "facodi_ai"])
        self.assertTrue(core["application"])
        self.assertFalse(website["application"])

    def test_pydantic_ai_is_pinned(self):
        requirements = (ROOT / "requirements.txt").read_text().splitlines()
        self.assertEqual(requirements, ["pydantic-ai-slim[openai,google]==2.39.0"])

    def test_ci_isolates_ai_dependencies_from_odoo_system_python(self):
        dockerfile = (ROOT / "docker" / "Dockerfile.ci").read_text()
        self.assertIn(
            "python3 -m venv --system-site-packages /opt/facodi-ai-venv",
            dockerfile,
        )
        self.assertNotIn("--ignore-installed", dockerfile)
        self.assertIn(
            "/opt/facodi-ai-venv/bin/python3 /usr/bin/odoo",
            dockerfile,
        )
        self.assertIn("websocket-client==1.8.0", dockerfile)
        self.assertIn("chromium", dockerfile)

    def test_website_translation_builder_contract(self):
        manifest = load_manifest("facodi_ai_website")
        builder_assets = manifest.get("assets", {}).get("website.website_builder_assets", [])
        unit_test_assets = manifest.get("assets", {}).get("web.assets_unit_tests", [])
        self.assertIn("facodi_ai_website/static/src/builder/**/*", builder_assets)
        self.assertIn("facodi_ai_website/static/tests/**/*", unit_test_assets)

        plugin_path = (
            ROOT
            / "facodi_ai_website"
            / "static"
            / "src"
            / "builder"
            / "facodi_ai_translation_plugin.js"
        )
        option_path = (
            ROOT
            / "facodi_ai_website"
            / "static"
            / "src"
            / "builder"
            / "facodi_ai_translation_option.xml"
        )
        self.assertTrue(plugin_path.exists())
        self.assertTrue(option_path.exists())
        plugin = plugin_path.read_text()
        option = option_path.read_text()

        for action_id in (
            "facodiTranslateUntranslatedAI",
            "facodiRetranslatePageAI",
            "facodiTranslateSelectedAI",
        ):
            self.assertIn(action_id, plugin)
            self.assertIn(action_id, option)
        self.assertIn('category("website-translation-plugins")', plugin)
        self.assertIn('"/facodi_ai/website/translate"', plugin)
        self.assertNotIn("/html_editor/generate_text", plugin)
        self.assertNotIn("/website/field/translation/update", plugin)

    def test_release_documentation_and_ci_gate(self):
        self.assertTrue((ROOT / "README.md").exists())
        self.assertTrue((ROOT / "docs" / "operations.md").exists())
        readme = (ROOT / "README.md").read_text()
        operations = (ROOT / "docs" / "operations.md").read_text()
        for required in (
            "facodi_ai",
            "facodi_ai_website",
            "Odoo 19 Community",
            "Translate untranslated",
            "Retranslate page",
            "Translate selected",
        ):
            self.assertIn(required, readme)
        self.assertIn("database backups", readme)
        self.assertIn("Standard Odoo fallback", operations)

        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        self.assertIn("Core-only install", workflow)
        self.assertIn("Clean install addons", workflow)
        self.assertIn("Upgrade addons", workflow)
        self.assertIn("git diff --check", workflow)
        self.assertIn("placeholder", workflow.lower())


if __name__ == "__main__":
    unittest.main()
