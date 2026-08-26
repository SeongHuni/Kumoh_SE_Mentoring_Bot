from __future__ import annotations

from backend.app.config import Settings
from backend.app.local_service import LocalHashProvider
from backend.app.openai_service import AIProvider, OpenAIProvider


def selected_provider_name(settings: Settings) -> str:
    if settings.ai_provider not in {"auto", "local", "openai"}:
        raise ValueError("AI_PROVIDER는 auto, local, openai 중 하나여야 합니다.")
    if settings.ai_provider == "auto":
        return "openai" if settings.openai_api_key else "local"
    return settings.ai_provider


def create_provider(settings: Settings) -> AIProvider:
    provider_name = selected_provider_name(settings)
    if provider_name == "local":
        return LocalHashProvider()
    if not settings.openai_api_key:
        raise RuntimeError("AI_PROVIDER=openai에는 OPENAI_API_KEY가 필요합니다.")
    return OpenAIProvider(
        api_key=settings.openai_api_key,
        embedding_model=settings.embedding_model,
        chat_model=settings.chat_model,
    )


def effective_models(settings: Settings) -> tuple[str, str]:
    if selected_provider_name(settings) == "local":
        return LocalHashProvider.chat_model, LocalHashProvider.embedding_model
    return settings.chat_model, settings.embedding_model
