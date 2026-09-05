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
