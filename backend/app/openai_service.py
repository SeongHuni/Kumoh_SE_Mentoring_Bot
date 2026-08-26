from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Protocol

from openai import OpenAI

from backend.app.answer_rules import ANSWER_RULES
from backend.app.domain import RetrievedChunk


class AIProvider(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

    def answer(self, question: str, contexts: Sequence[RetrievedChunk]) -> str: ...

    def chat_json(
        self, *, system: str, user: str, schema: dict, schema_name: str
    ) -> dict: ...


def build_context_block(contexts: Sequence[RetrievedChunk]) -> str:
    """참고 자료 블록.

    번호 [1], [2] 는 contexts 의 순서 그대로다. 답변 본문의 인용 번호와
    화면의 출처 목록이 이 순서를 공유하므로, 중간에서 걸러내거나 재정렬하면
    번호가 어긋난다.
    """
    blocks = []
    for index, item in enumerate(contexts, start=1):
        chunk = item.chunk
        head = " | ".join(
            part for part in (chunk.title, chunk.source, chunk.published_at or "") if part
        )
        blocks.append(f"[{index}] ({head})\n{chunk.text}")
    return "\n\n---\n\n".join(blocks)


class OpenAIProvider:
    def __init__(
        self,
        *,
        api_key: str,
        embedding_model: str,
        chat_model: str,
        batch_size: int = 64,
        client: OpenAI | None = None,
    ) -> None:
        self.embedding_model = embedding_model
        self.chat_model = chat_model
        self.batch_size = batch_size
        self.client = client or OpenAI(api_key=api_key)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        normalized = [text.replace("\n", " ").strip() for text in texts]
        if not normalized or any(not text for text in normalized):
            raise ValueError("임베딩 입력은 비어 있을 수 없습니다.")
        embeddings: list[list[float]] = []
        for start in range(0, len(normalized), self.batch_size):
            batch = normalized[start : start + self.batch_size]
            response = self.client.embeddings.create(
                model=self.embedding_model,
                input=batch,
                encoding_format="float",
            )
            ordered = sorted(response.data, key=lambda item: item.index)
            embeddings.extend(item.embedding for item in ordered)
        return embeddings

    def answer(self, question: str, contexts: Sequence[RetrievedChunk]) -> str:
        """검색된 자료만 근거로 답한다.

        지시문은 answer_rules.ANSWER_RULES 에 따로 두었다. 규칙 하나하나가
        실패 사례에서 나왔고 근거를 주석으로 남겨야 해서다.
        """
        response = self.client.chat.completions.create(
            model=self.chat_model,
            temperature=0,
            max_tokens=700,
            messages=[
                {"role": "system", "content": ANSWER_RULES},
                {
                    "role": "user",
                    "content": (
                        f"질문: {question}\n\n"
                        f"참고 자료:\n{build_context_block(contexts)}"
                    ),
                },
            ],
        )
        answer = (response.choices[0].message.content or "").strip()
        if not answer:
            raise RuntimeError("OpenAI가 빈 답변을 반환했습니다.")
        return answer

    def chat_json(self, *, system: str, user: str, schema: dict, schema_name: str) -> dict:
        """검색 계획기용. 스키마를 강제해 JSON 만 받는다."""
        response = self.client.chat.completions.create(
            model=self.chat_model,
            temperature=0,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": True},
            },
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return json.loads(response.choices[0].message.content or "{}")
