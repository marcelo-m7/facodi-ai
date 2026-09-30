import ast
import glob
import pathlib
import unittest
import xml.etree.ElementTree as ET
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_manifest(addon):
    path = ROOT / addon / "__manifest__.py"
    return ast.literal_eval(path.read_text())


class RepositoryContractTest(unittest.TestCase):
    def test_addon_boundaries(self):
        core = load_manifest("facodi_ai")
        learning = load_manifest("facodi_ai_learning")
        website = load_manifest("facodi_ai_website")
        self.assertNotIn("facodi_learning", core["depends"])
        self.assertNotIn("website", core["depends"])
        self.assertNotIn("website_slides", core["depends"])
        self.assertEqual(learning["depends"], ["facodi_ai", "facodi_learning"])
        self.assertEqual(website["depends"], ["website", "facodi_ai"])
        self.assertTrue(core["application"])
        self.assertFalse(learning["application"])
        self.assertFalse(website["application"])


    def test_odoo_manifest_data_and_assets_resolve(self):
        for addon in ("facodi_ai", "facodi_ai_learning", "facodi_ai_website"):
            with self.subTest(addon=addon):
                manifest = load_manifest(addon)
                addon_root = ROOT / addon
                data_paths = [*manifest.get("data", []), *manifest.get("demo", [])]
                duplicates = sorted(
                    path for path, count in Counter(data_paths).items() if count > 1
                )
                self.assertFalse(
                    duplicates,
                    f"{addon} has duplicate manifest data entries: {duplicates}",
                )
                missing = sorted(
                    path for path in data_paths if not (addon_root / path).is_file()
                )
                self.assertFalse(
                    missing,
                    f"{addon} manifest references missing data files: {missing}",
                )

                missing_assets = []
                for bundle, entries in manifest.get("assets", {}).items():
                    for entry in entries:
                        pattern = str(ROOT / entry)
                        if glob.has_magic(pattern):
                            if not glob.glob(pattern, recursive=True):
                                missing_assets.append(f"{bundle}: {entry}")
                        elif not pathlib.Path(pattern).is_file():
                            missing_assets.append(f"{bundle}: {entry}")
                self.assertFalse(
                    missing_assets,
                    f"{addon} manifest assets do not resolve: {missing_assets}",
                )

    def test_odoo_xml_is_well_formed_and_external_ids_are_unique_per_addon(self):
        external_id_tags = {"record", "template", "menuitem"}
        for addon in ("facodi_ai", "facodi_ai_learning", "facodi_ai_website"):
            with self.subTest(addon=addon):
                manifest = load_manifest(addon)
                owners = {}
                duplicates = []
                for relative_path in [
                    *manifest.get("data", []),
                    *manifest.get("demo", []),
                ]:
                    if not relative_path.endswith(".xml"):
                        continue
                    root = ET.parse(ROOT / addon / relative_path).getroot()
                    for element in root.iter():
                        external_id = element.attrib.get("id")
                        if element.tag not in external_id_tags or not external_id:
                            continue
                        previous = owners.setdefault(external_id, relative_path)
                        if previous != relative_path:
                            duplicates.append(
                                (external_id, previous, relative_path)
                            )
                self.assertFalse(
                    duplicates,
                    f"{addon} duplicate external IDs across manifest XML files: {duplicates}",
                )

    def test_reusable_core_contains_no_learning_model_references(self):
        forbidden = (
            "facodi_learning",
            "website_slides",
            "slide.channel",
            "slide.slide",
            "facodi.learning.",
            "facodi.ai.learning.",
        )
        roots = [
            ROOT / "facodi_ai" / "models",
            ROOT / "facodi_ai" / "data",
            ROOT / "facodi_ai" / "security",
            ROOT / "facodi_ai" / "views",
        ]
        violations = []
        for root in roots:
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix not in {".py", ".xml", ".csv"}:
                    continue
                text = path.read_text(encoding="utf-8")
                for value in forbidden:
                    if value in text:
                        violations.append(f"{path.relative_to(ROOT)}: {value}")
        self.assertFalse(
            violations,
            "reusable facodi_ai core still contains learning coupling: "
            + ", ".join(violations),
        )

    def test_learning_bridge_migration_contract(self):
        migration = (
            ROOT
            / "facodi_ai"
            / "migrations"
            / "19.0.2.0.0"
            / "pre-migrate.py"
        ).read_text(encoding="utf-8")
        self.assertIn("module = 'facodi_ai_learning'", migration)
        self.assertIn("module = 'facodi_ai'", migration)
        self.assertIn("ir_cron_facodi_ai_learning_jobs", migration)
        self.assertIn("model_facodi_ai_learning_job", migration)

        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "Checkout legacy facodi-ai layout for real migration test",
            workflow,
        )
        self.assertIn(
            "756e48cc447f82280e8b9ad0958b516d0d45fc87",
            workflow,
        )
        self.assertIn(
            "ci_seed_learning_bridge_upgrade.py",
            workflow,
        )
        self.assertIn(
            "ci_verify_learning_bridge_upgrade.py",
            workflow,
        )
        self.assertIn(
            "--init=facodi_ai_learning",
            workflow,
        )

    def test_core_only_ci_does_not_expose_facodi_learning_addons_path(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        start = workflow.index("- name: Core-only install")
        end = workflow.index("- name: Reset database after core-only install")
        core_only = workflow[start:end]
        self.assertIn(
            "--addons-path=/mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons",
            core_only,
        )
        self.assertNotIn(".ci/facodi-learning", core_only)
        self.assertIn("--init=facodi_ai", core_only)

    def test_github_actions_are_commit_pinned(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        for expected in (
            "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
            "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065",
            "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
        ):
            self.assertIn(expected, workflow)
        for mutable in (
            "actions/checkout@v4",
            "actions/setup-python@v5",
            "actions/upload-artifact@v4",
        ):
            self.assertNotIn(mutable, workflow)

    def test_pydantic_ai_is_pinned(self):
        requirements = (ROOT / "requirements.txt").read_text().splitlines()
        self.assertEqual(requirements, ["pydantic-ai-slim[openai,google]==2.39.0"])

    def test_facodi_learning_ci_baseline_is_explicit_and_current(self):
        workflow = (
            ROOT / ".github" / "workflows" / "ci.yml"
        ).read_text(encoding="utf-8")
        expected = "4c1a2886d91280247765ec778c4cd2d5c6b37ff8"
        self.assertIn("repository: marcelo-m7/facodi-learning", workflow)
        self.assertIn(f"ref: {expected}", workflow)
        self.assertNotIn(
            "ref: 38ba9b0c7fe4964f9bcd73978b9adf5407dc3425",
            workflow,
        )

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
        self.assertNotIn('"valueHistory"', plugin)
        self.assertIn("element.value = value", plugin)
        self.assertNotIn("/html_editor/generate_text", plugin)
        self.assertNotIn("/website/field/translation/update", plugin)

    def test_release_documentation_and_ci_gate(self):
        self.assertTrue((ROOT / "README.md").exists())
        self.assertTrue((ROOT / "docs" / "operations.md").exists())
        readme = (ROOT / "README.md").read_text()
        operations = (ROOT / "docs" / "operations.md").read_text()
        for required in (
            "facodi_ai",
            "facodi_ai_learning",
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
        self.assertIn("facodi_ai,facodi_ai_learning,facodi_ai_website", workflow)
        self.assertIn("Upgrade addons", workflow)
        self.assertIn("Verify bridge rows and XML IDs survived migration", workflow)
        self.assertIn("git diff --check", workflow)
        self.assertIn("placeholder", workflow.lower())


if __name__ == "__main__":
    unittest.main()
