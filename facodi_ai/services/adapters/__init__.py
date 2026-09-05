from ..provider_registry import provider_registry
from .gemini import GeminiAdapter
from .openai import OpenAIAdapter


for _key, _adapter in (
    ("openai", OpenAIAdapter),
    ("gemini", GeminiAdapter),
):
    if _key not in provider_registry.keys():
        provider_registry.register(_key, _adapter)


__all__ = ["GeminiAdapter", "OpenAIAdapter"]
