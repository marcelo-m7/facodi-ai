from .errors import ConfigurationError


class ProviderAdapterRegistry:
    def __init__(self):
        self._adapters = {}

    def register(self, key, adapter_cls):
        if not key:
            raise ConfigurationError("Provider adapter key is required.")
        if key in self._adapters:
            raise ConfigurationError(f"Provider adapter '{key}' is already registered.")
        self._adapters[key] = adapter_cls
        return adapter_cls

    def get(self, key):
        try:
            return self._adapters[key]
        except KeyError as exc:
            raise ConfigurationError(
                f"Provider adapter '{key}' is not registered."
            ) from exc

    def keys(self):
        return tuple(self._adapters)


provider_registry = ProviderAdapterRegistry()
