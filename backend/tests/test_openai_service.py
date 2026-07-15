from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from backend.app.openai_service import OpenAIProvider


def test_openai_embeddings_send_configured_dimensions_and_preserve_order() -> None:
    create = Mock(
        return_value=SimpleNamespace(
            data=[
                SimpleNamespace(index=1, embedding=[0.0, 1.0]),
                SimpleNamespace(index=0, embedding=[1.0, 0.0]),
            ]
        )
    )
    client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
    provider = OpenAIProvider(
        api_key="test-key",
        embedding_model="test-embedding",
        chat_model="test-chat",
        dimensions=2,
        client=client,
    )

    result = provider.embed(["첫 번째", "두 번째"])

    assert result == [[1.0, 0.0], [0.0, 1.0]]
    create.assert_called_once_with(
        model="test-embedding",
        input=["첫 번째", "두 번째"],
        encoding_format="float",
        dimensions=2,
    )


@pytest.mark.parametrize("texts", [[], ["   "]])
def test_openai_embeddings_reject_empty_inputs(texts) -> None:
    client = SimpleNamespace(embeddings=SimpleNamespace(create=Mock()))
    provider = OpenAIProvider(
        api_key="test-key",
        embedding_model="test-embedding",
        chat_model="test-chat",
        dimensions=256,
        client=client,
    )

    with pytest.raises(ValueError, match="비어"):
        provider.embed(texts)

    client.embeddings.create.assert_not_called()
