from abc import ABC, abstractmethod


class BaseProviderAdapter(ABC):
    @abstractmethod
    def run_structured(
        self,
        resolved,
        api_key,
        instructions,
        user_prompt,
        output_type,
    ):
        """Run one structured AI request and return (output, usage)."""
        raise NotImplementedError
