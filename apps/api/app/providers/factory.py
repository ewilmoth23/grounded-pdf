from app.core.config import Settings
from app.core.exceptions import ProviderUnavailableError
from app.providers.base import ChatProvider
from app.providers.mock import MockChatProvider
from app.providers.ollama import OllamaProvider
from app.providers.openai_compatible import OpenAICompatibleProvider


def create_chat_provider(settings: Settings) -> ChatProvider:
    if settings.model_provider == "ollama":
        return OllamaProvider(settings)
    if settings.model_provider == "openai_compatible":
        return OpenAICompatibleProvider(settings)
    if settings.model_provider == "mock" and settings.environment == "test":
        return MockChatProvider()
    raise ProviderUnavailableError("The configured model provider is not available")
