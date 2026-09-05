from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from .base import BaseProviderAdapter


def _usage_dict(result):
    usage = result.usage() if callable(getattr(result, "usage", None)) else getattr(result, "usage", None)
    return {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
    }


class OpenAIAdapter(BaseProviderAdapter):
    def run_structured(
        self,
        resolved,
        api_key,
        instructions,
        user_prompt,
        output_type,
    ):
        provider = OpenAIProvider(api_key=api_key)
        model = OpenAIResponsesModel(resolved.model_name, provider=provider)
        settings = {
            "timeout": resolved.timeout,
            "max_tokens": resolved.max_tokens,
        }
        if resolved.temperature is not None:
            settings["temperature"] = resolved.temperature
        agent = Agent(
            model,
            output_type=output_type,
            instructions=instructions,
            retries=resolved.retries,
            model_settings=settings,
        )
        result = agent.run_sync(user_prompt)
        return result.output, _usage_dict(result)
