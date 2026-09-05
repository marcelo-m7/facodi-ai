from odoo import api, models


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
        return self.env["ir.config_parameter"].sudo().get_param(
            self._parameter_key(connection),
            False,
        )

    @api.model
    def _has_connection_api_key(self, connection):
        return bool(self._get_connection_api_key(connection))

    @api.model
    def _delete_connection_api_key(self, connection):
        self.env["ir.config_parameter"].sudo().set_param(
            self._parameter_key(connection),
            False,
        )
