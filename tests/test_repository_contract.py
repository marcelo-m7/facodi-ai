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


if __name__ == "__main__":
    unittest.main()
