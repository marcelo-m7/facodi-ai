from copy import deepcopy
from types import MappingProxyType

PROVIDER_DEFAULTS = MappingProxyType(
    {
        "openai": MappingProxyType({"model": "gpt-5.6-luna"}),
        "gemini": MappingProxyType({"model": "gemini-3.8-flash"}),
    }
)

PROFILE_DEFAULTS = MappingProxyType(
    {
        "website_translation": MappingProxyType(
            {
                "provider": "gemini",
                "timeout": 60,
                "max_tokens": 8192,
                "retries": 2,
                "structured_output": True,
                "temperature": None,
            }
        )
    }
)


def get_profile_defaults(code):
    values = PROFILE_DEFAULTS.get(code)
    if values is None:
        return {}
    result = dict(values)
    result["provider_models"] = {
        key: provider["model"] for key, provider in PROVIDER_DEFAULTS.items()
    }
    return deepcopy(result)
