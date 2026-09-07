import os
from dataclasses import dataclass

from odoo import api, models

from .provider_registry import provider_registry


@dataclass(frozen=True)
class CredentialResolution:
    source: str
    api_key: str | bool
    environment_name: str | bool
    stored_credential_present: bool

    @property
    def configured(self):
        return bool(self.api_key)


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
    def _get_stored_connection_api_key(self, connection):
        return self.env["ir.config_parameter"].sudo().get_param(
            self._parameter_key(connection),
            False,
        )

    @api.model
    def _resolve_connection_credential(self, connection):
        provider = connection.provider_id
        adapter_key = provider.adapter_key if provider else False
        metadata = (
            provider_registry.metadata(adapter_key)
            if adapter_key in provider_registry.keys()
            else {}
        )
        environment_name = metadata.get("credential_env")
        environment_key = os.environ.get(environment_name) if environment_name else False
        stored_key = self._get_stored_connection_api_key(connection)
        if environment_key:
            return CredentialResolution(
                source="environment",
                api_key=environment_key,
                environment_name=environment_name,
                stored_credential_present=bool(stored_key),
            )
        if stored_key:
            return CredentialResolution(
                source="odoo",
                api_key=stored_key,
                environment_name=False,
                stored_credential_present=True,
            )
        return CredentialResolution(
            source="none",
            api_key=False,
            environment_name=environment_name or False,
            stored_credential_present=False,
        )

    @api.model
    def _get_connection_api_key(self, connection):
        return self._resolve_connection_credential(connection).api_key

    @api.model
    def _has_connection_api_key(self, connection):
        return self._resolve_connection_credential(connection).configured

    @api.model
    def _has_stored_connection_api_key(self, connection):
        return bool(self._get_stored_connection_api_key(connection))

    @api.model
    def _delete_connection_api_key(self, connection):
        self.env["ir.config_parameter"].sudo().set_param(
            self._parameter_key(connection),
            False,
        )
