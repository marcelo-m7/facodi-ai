from pydantic import BaseModel, ConfigDict

from odoo import api, models

from .defaults import get_profile_defaults, get_provider_defaults
from .errors import ConfigurationError


class ResolvedAIProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile_id: int
    provider_code: str
    connection_id: int | None
    model_name: str
    timeout: int
    max_tokens: int
    retries: int
    structured_output: bool
    temperature: float | None


class FacodiAIProfileResolver(models.AbstractModel):
    _name = "facodi.ai.profile.resolver"
    _description = "FACODI AI Profile Resolver"

    @api.model
    def _resolve(self, profile):
        profile.ensure_one()
        defaults = get_profile_defaults(profile.code)

        provider = profile.connection_id.provider_id or profile.provider_id
        if not provider and defaults.get("provider"):
            provider = self.env["facodi.ai.provider"].search(
                [
                    ("code", "=", defaults["provider"]),
                    ("active", "=", True),
                ],
                limit=1,
            )
        if not provider:
            global_code = self.env["ir.config_parameter"].sudo().get_param(
                "facodi_ai.default_provider"
            )
            if global_code:
                provider = self.env["facodi.ai.provider"].search(
                    [
                        ("code", "=", global_code),
                        ("active", "=", True),
                    ],
                    limit=1,
                )
        if not provider:
            raise ConfigurationError("No AI provider is configured for this profile.")

        connection = profile.connection_id
        if not connection:
            connection = self.env["facodi.ai.connection"].search(
                [
                    ("provider_id", "=", provider.id),
                    ("active", "=", True),
                    ("is_default", "=", True),
                ],
                limit=1,
            )
        if not connection:
            candidates = self.env["facodi.ai.connection"].search(
                [
                    ("provider_id", "=", provider.id),
                    ("active", "=", True),
                ]
            )
            if len(candidates) == 1:
                connection = candidates

        provider_defaults = get_provider_defaults(provider.code)
        model_name = profile.model_override or provider_defaults.get("model")
        if not model_name:
            raise ConfigurationError(
                f"No model is configured for AI provider '{provider.code}'."
            )

        structured_output = (
            profile.structured_output_override == "enabled"
            if profile.structured_output_override != "default"
            else defaults.get("structured_output", True)
        )

        return ResolvedAIProfile(
            profile_id=profile.id,
            provider_code=provider.code,
            connection_id=connection.id or None,
            model_name=model_name,
            timeout=profile.timeout_override or defaults.get("timeout", 60),
            max_tokens=profile.max_tokens_override or defaults.get("max_tokens", 8192),
            retries=profile.retries_override or defaults.get("retries", 2),
            structured_output=structured_output,
            temperature=(
                profile.temperature_override
                if profile.temperature_overridden
                else defaults.get("temperature")
            ),
        )
