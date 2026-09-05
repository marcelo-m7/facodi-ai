import os

from odoo import api, models


_PROVIDER_ENV_KEYS = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
}


class FacodiAISecretStore(models.AbstractModel):
    _name = "facodi.ai.secret.store"
    _description = "FACODI AI Secret Store"

    @api.model
    def _parameter_key(self, connection):
        return f"facodi_ai.connection.{connection.credential_uuid}.api_key"

    @api.model
    def _set_connection_api_key(self, connection, value):
        params = self.env["ir.config_parameter"].sudo()
        key = self._parameter_key(connection)
        if value:
            params.set_param(key, value)
        else:
            params.set_param(key, False)

    @api.model
    def _get_connection_api_key(self, connection):
        database_key = self.env["ir.config_parameter"].sudo().get_param(
            self._parameter_key(connection),
            False,
        )
        if database_key:
            return database_key

        provider_code = connection.provider_id.code if connection.provider_id else False
        environment_name = _PROVIDER_ENV_KEYS.get(provider_code)
        if not environment_name:
            return False
        return os.environ.get(environment_name) or False

    @api.model
    def _has_connection_api_key(self, connection):
        return bool(self._get_connection_api_key(connection))

    @api.model
    def _delete_connection_api_key(self, connection):
        self.env["ir.config_parameter"].sudo().set_param(
            self._parameter_key(connection),
            False,
        )
