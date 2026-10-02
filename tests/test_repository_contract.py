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
        retired = load_manifest("facodi_ai_website")
        self.assertNotIn("facodi_learning", core["depends"])
        self.assertNotIn("website", core["depends"])
        self.assertNotIn("website_slides", core["depends"])
        self.assertEqual(learning["depends"], ["facodi_ai", "facodi_learning"])
        self.assertEqual(retired["depends"], [])
        self.assertFalse(retired["installable"])
        self.assertTrue(core["application"])
        self.assertFalse(learning["application"])
        self.assertFalse(retired["application"])


    def test_odoo_manifest_data_and_assets_resolve(self):
        for addon in ("facodi_ai", "facodi_ai_learning"):
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
        for addon in ("facodi_ai", "facodi_ai_learning"):
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
        self.assertIn("name LIKE \'%facodi_ai_learning%\'", migration)

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

    def test_learning_job_idempotency_upgrade_contract(self):
        model = (
            ROOT
            / "facodi_ai_learning"
            / "models"
            / "learning_suggestion.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "unique(source_channel_id, source_hash)",
            model,
        )
        self.assertIn(
            "unique(source_slide_id, source_hash)",
            model,
        )
        self.assertNotIn(
            "unique(source_channel_id, source_slide_id, source_hash)",
            model,
        )

        migration = (
            ROOT
            / "facodi_ai_learning"
            / "migrations"
            / "19.0.1.1.0"
            / "pre-migrate.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "PARTITION BY source_channel_id, source_slide_id, source_hash",
            migration,
        )
        self.assertIn(
            "UPDATE facodi_ai_learning_analysis AS analysis",
            migration,
        )
        self.assertIn(
            "DELETE FROM facodi_ai_learning_job AS job",
            migration,
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
        expected = "159b2868a92a9f821910667290f6da5733103f32"
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

    def test_legacy_website_translation_shell_is_retired(self):
        manifest = load_manifest("facodi_ai_website")
        self.assertFalse(manifest.get("installable", True))
        self.assertEqual(manifest.get("depends", ["website"]), [])
        self.assertEqual(manifest.get("data", ["unexpected"]), [])
        self.assertEqual(manifest.get("assets", {"unexpected": ["x"]}), {})
        self.assertFalse((ROOT / "facodi_ai_website" / "controllers").exists())
        self.assertFalse((ROOT / "facodi_ai_website" / "models").exists())
        self.assertFalse((ROOT / "facodi_ai_website" / "services").exists())
        self.assertFalse((ROOT / "facodi_ai_website" / "static").exists())
        self.assertFalse((ROOT / "facodi_ai_website" / "views").exists())
        self.assertFalse((ROOT / "facodi_ai_website" / "data").exists())

    def test_release_documentation_and_ci_gate(self):
        self.assertTrue((ROOT / "README.md").exists())
        self.assertTrue((ROOT / "docs" / "operations.md").exists())
        readme = (ROOT / "README.md").read_text()
        operations = (ROOT / "docs" / "operations.md").read_text()
        for required in (
            "facodi_ai",
            "facodi_ai_learning",
            "Odoo 19 Community",
            "native Odoo Website translation",
        ):
            self.assertIn(required, readme)
        self.assertIn("database backups", readme)
        self.assertIn("Standard Odoo fallback", operations)

        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        self.assertIn("Core-only install", workflow)
        self.assertIn("Clean install addons", workflow)
        self.assertIn("facodi_ai,facodi_ai_learning", workflow)
        self.assertIn("Upgrade addons", workflow)
        self.assertIn("Verify bridge rows and XML IDs survived migration", workflow)
        self.assertIn("git diff --check", workflow)
        self.assertIn("placeholder", workflow.lower())


if __name__ == "__main__":
    unittest.main()
