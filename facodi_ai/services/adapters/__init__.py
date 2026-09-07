from ..provider_registry import provider_registry
from .gemini import GeminiAdapter
from .openai import OpenAIAdapter


for _key, _adapter, _credential_env in (
    ("openai", OpenAIAdapter, "OPENAI_API_KEY"),
    ("gemini", GeminiAdapter, "GEMINI_API_KEY"),
):
    if _key not in provider_registry.keys():
        provider_registry.register(_key, _adapter, credential_env=_credential_env)


__all__ = ["GeminiAdapter", "OpenAIAdapter"]
