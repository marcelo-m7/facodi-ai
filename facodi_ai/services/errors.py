class FacodiAIError(Exception):
    code = "internal_error"


class ConfigurationError(FacodiAIError):
    code = "configuration_error"


class AuthenticationError(FacodiAIError):
    code = "authentication_error"


class ProviderError(FacodiAIError):
    code = "provider_error"


class RateLimitError(FacodiAIError):
    code = "rate_limit"


class TimeoutError(FacodiAIError):
    code = "timeout"


class ValidationError(FacodiAIError):
    code = "validation_error"


class UnsupportedCapabilityError(FacodiAIError):
    code = "unsupported_capability"
