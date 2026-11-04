from abc import ABC, abstractmethod


class ProviderError(Exception):
    """kind: not_configured | rate_limit | timeout | server | auth | bad_request | invalid_output"""

    def __init__(self, kind: str, message: str = "", retry_after: float | None = None):
        super().__init__(message or kind)
        self.kind, self.retry_after = kind, retry_after


USER_MESSAGES = {
    "not_configured": "No AI provider is configured on this server.",
    "rate_limit": "The AI service is busy (rate limit reached). Try again in a minute.",
    "timeout": "The AI service took too long to respond.",
    "server": "The AI service had a problem. Try again shortly.",
    "auth": "The AI service rejected this server's credentials. The administrator needs to check the API key.",
    "bad_request": "The AI service could not process this photo.",
    "invalid_output": "The AI service returned an unusable result.",
}


class AIProvider(ABC):
    name = "provider"

    @abstractmethod
    def edit(self, image_png: bytes, prompt: str, size: tuple[int, int]) -> bytes:
        """Return the edited image as encoded bytes. Raise ProviderError on any failure."""
