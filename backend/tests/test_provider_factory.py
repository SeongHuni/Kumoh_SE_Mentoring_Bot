from dataclasses import replace
from unittest.mock import Mock

import pytest
from backend.app import provider_factory
from backend.app.config import get_settings
from backend.app.local_service import LocalHashProvider


def test_local_provider_receives_configured_dimensions() -> None:
    settings = replace(get_settings(), ai_provider="local", embedding_dimensions=384)

    provider = provider_factory.create_provider(settings)

    assert isinstance(provider, LocalHashProvider)
    assert provider.dimensions == 384


def test_openai_provider_receives_models_key_and_dimensions(monkeypatch) -> None:
    constructor = Mock(return_value=object())
    monkeypatch.setattr(provider_factory, "OpenAIProvider", constructor)
    settings = replace(
        get_settings(),
        ai_provider="openai",
        openai_api_key="test-key",
        embedding_dimensions=768,
    )

    provider_factory.create_provider(settings)

    constructor.assert_called_once_with(
        api_key="test-key",
        embedding_model=settings.embedding_model,
        chat_model=settings.chat_model,
        dimensions=768,
    )


def test_explicit_openai_provider_requires_key() -> None:
    settings = replace(get_settings(), ai_provider="openai", openai_api_key=None)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        provider_factory.create_provider(settings)


@pytest.mark.parametrize(
    ("api_key", "expected"),
    [(None, "local"), ("test-key", "openai")],
)
def test_auto_provider_uses_key_presence(api_key, expected) -> None:
    settings = replace(get_settings(), ai_provider="auto", openai_api_key=api_key)

    assert provider_factory.selected_provider_name(settings) == expected
