import os
from unittest.mock import patch

from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAIConnection(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Provider = self.env["facodi.ai.provider"]
        self.Connection = self.env["facodi.ai.connection"]
        self.openai = self.env.ref("facodi_ai.provider_openai")
        self.gemini = self.env.ref("facodi_ai.provider_gemini")

    def test_multiple_connections_per_provider(self):
        first = self.Connection.create(
            {"name": "OpenAI Production", "provider_id": self.openai.id}
        )
        second = self.Connection.create(
            {"name": "OpenAI Development", "provider_id": self.openai.id}
        )
        self.assertNotEqual(first.credential_uuid, second.credential_uuid)
        self.assertEqual(
            self.Connection.search_count([("provider_id", "=", self.openai.id)]),
            2,
        )

    def test_provider_code_is_unique(self):
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.Provider.create(
                {
                    "name": "Duplicate OpenAI",
                    "code": "openai",
                    "adapter_key": "openai",
                }
            )

    def test_only_one_default_connection_per_provider(self):
        first = self.Connection.create(
            {
                "name": "Primary",
                "provider_id": self.openai.id,
                "is_default": True,
            }
        )
        second = self.Connection.create(
            {
                "name": "Secondary",
                "provider_id": self.openai.id,
                "is_default": True,
            }
        )
        self.env.invalidate_all()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)

    def test_api_key_is_write_only_and_stored_in_config_parameter(self):
        connection = self.Connection.create(
            {"name": "Secret Test", "provider_id": self.openai.id}
        )
        connection.write({"api_key": "sk-facodi-test-secret"})
        self.env.invalidate_all()
        connection = self.Connection.browse(connection.id)
        self.assertFalse(connection.api_key)
        self.assertTrue(connection.api_key_configured)
        parameter_key = (
            f"facodi_ai.connection.{connection.credential_uuid}.api_key"
        )
        self.assertEqual(
            self.env["ir.config_parameter"].sudo().get_param(parameter_key),
            "sk-facodi-test-secret",
        )

    def test_credential_uuid_is_immutable(self):
        connection = self.Connection.create(
            {"name": "Immutable", "provider_id": self.openai.id}
        )
        with self.assertRaises(ValidationError):
            connection.write({"credential_uuid": "replaced"})

    def test_unlink_removes_secret(self):
        connection = self.Connection.create(
            {"name": "Disposable", "provider_id": self.openai.id}
        )
        connection.write({"api_key": "secret-to-delete"})
        parameter_key = (
            f"facodi_ai.connection.{connection.credential_uuid}.api_key"
        )
        connection.unlink()
        self.assertFalse(
            self.env["ir.config_parameter"].sudo().get_param(parameter_key)
        )

    def test_gemini_environment_key_is_fallback_when_database_key_is_empty(self):
        connection = self.Connection.create(
            {"name": "Gemini Environment", "provider_id": self.gemini.id}
        )
        with patch.dict(os.environ, {"GEMINI_API_KEY": "env-gemini-secret"}, clear=False):
            self.assertEqual(
                self.env["facodi.ai.secret.store"]._get_connection_api_key(connection),
                "env-gemini-secret",
            )

    def test_environment_key_takes_precedence_over_database_key(self):
        connection = self.Connection.create(
            {"name": "Gemini Database", "provider_id": self.gemini.id}
        )
        connection.write({"api_key": "db-gemini-secret"})
        with patch.dict(os.environ, {"GEMINI_API_KEY": "env-gemini-secret"}, clear=False):
            self.assertEqual(
                self.env["facodi.ai.secret.store"]._get_connection_api_key(connection),
                "env-gemini-secret",
            )

    def test_credential_status_reports_environment_without_exposing_secret(self):
        connection = self.Connection.create(
            {"name": "OpenAI Runtime", "provider_id": self.openai.id}
        )
        connection.write({"api_key": "db-openai-secret"})
        with patch.dict(os.environ, {"OPENAI_API_KEY": "env-openai-secret"}, clear=False):
            self.env.invalidate_all()
            connection = self.Connection.browse(connection.id)
            self.assertTrue(connection.api_key_configured)
            self.assertTrue(connection.stored_api_key_configured)
            self.assertEqual(connection.credential_source, "environment")
            self.assertEqual(connection.credential_env_name, "OPENAI_API_KEY")
            values = connection.read([
                "api_key",
                "api_key_configured",
                "stored_api_key_configured",
                "credential_source",
                "credential_env_name",
            ])[0]
            self.assertNotIn("env-openai-secret", repr(values))
            self.assertNotIn("db-openai-secret", repr(values))

    def test_database_key_is_used_when_environment_is_absent(self):
        connection = self.Connection.create(
            {"name": "OpenAI Database", "provider_id": self.openai.id}
        )
        connection.write({"api_key": "db-openai-secret"})
        with patch.dict(os.environ, {}, clear=True):
            self.env.invalidate_all()
            connection = self.Connection.browse(connection.id)
            self.assertTrue(connection.api_key_configured)
            self.assertEqual(connection.credential_source, "odoo")
            self.assertFalse(connection.credential_env_name)

    def test_removing_database_key_does_not_remove_environment_key(self):
        connection = self.Connection.create(
            {"name": "Gemini Runtime", "provider_id": self.gemini.id}
        )
        connection.write({"api_key": "db-gemini-secret"})
        with patch.dict(os.environ, {"GEMINI_API_KEY": "env-gemini-secret"}, clear=False):
            connection.action_remove_stored_api_key()
            self.env.invalidate_all()
            connection = self.Connection.browse(connection.id)
            self.assertTrue(connection.api_key_configured)
            self.assertFalse(connection.stored_api_key_configured)
            self.assertEqual(connection.credential_source, "environment")
            self.assertEqual(os.environ["GEMINI_API_KEY"], "env-gemini-secret")

    def test_no_credential_is_reported_as_unconfigured(self):
        connection = self.Connection.create(
            {"name": "Unconfigured OpenAI", "provider_id": self.openai.id}
        )
        with patch.dict(os.environ, {}, clear=True):
            self.env.invalidate_all()
            connection = self.Connection.browse(connection.id)
            self.assertFalse(connection.api_key_configured)
            self.assertFalse(connection.stored_api_key_configured)
            self.assertEqual(connection.credential_source, "none")
            self.assertEqual(connection.credential_env_name, "OPENAI_API_KEY")

    def test_openai_environment_key_is_supported_symmetrically(self):
        connection = self.Connection.create(
            {"name": "OpenAI Environment", "provider_id": self.openai.id}
        )
        with patch.dict(os.environ, {"OPENAI_API_KEY": "env-openai-secret"}, clear=False):
            self.assertEqual(
                self.env["facodi.ai.secret.store"]._get_connection_api_key(connection),
                "env-openai-secret",
            )

    def test_unknown_provider_does_not_read_generic_environment_secrets(self):
        provider = self.Provider.create(
            {
                "name": "Custom Provider",
                "code": "custom_provider",
                "adapter_key": "custom_provider",
            }
        )
        connection = self.Connection.create(
            {"name": "Custom", "provider_id": provider.id}
        )
        with patch.dict(
            os.environ,
            {
                "GEMINI_API_KEY": "env-gemini-secret",
                "OPENAI_API_KEY": "env-openai-secret",
            },
            clear=False,
        ):
            self.assertFalse(
                self.env["facodi.ai.secret.store"]._get_connection_api_key(connection)
            )
