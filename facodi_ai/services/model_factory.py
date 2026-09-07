from .errors import ConfigurationError
from .provider_registry import provider_registry


def build_provider_adapter(provider):
    if not provider or not provider.exists():
        raise ConfigurationError("AI provider is missing.")
    if not provider.active:
        raise ConfigurationError("AI provider is disabled.")
    if not provider.adapter_key:
        raise ConfigurationError("AI provider adapter is not configured.")
    adapter_cls = provider_registry.get(provider.adapter_key)
    return adapter_cls()
