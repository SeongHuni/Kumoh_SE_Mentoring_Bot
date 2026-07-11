from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from openai import OpenAI

from backend.app.domain import RetrievedChunk


class AIProvider(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

    def answer(self, question: str, contexts: Sequence[RetrievedChunk]) -> str: ...


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
        context_text = "\n\n".join(
            (
                f"[자료 {index}]\n"
                f"제목: {item.chunk.title}\n"
                f"작성일: {item.chunk.published_at or '알 수 없음'}\n"
                f"출처: {item.chunk.source}\n"
                f"내용: {item.chunk.text}"
            )
            for index, item in enumerate(contexts, start=1)
        )
        response = self.client.responses.create(
            model=self.chat_model,
            store=False,
            max_output_tokens=700,
            instructions=(
                "당신은 금오공과대학교 소프트웨어전공 학생을 돕는 SE 멘토입니다. "
                "제공된 자료에 명시된 사실만 사용해 한국어로 답하세요. "
                "자료에 답이 없거나 서로 충돌하면 그 사실을 분명히 말하고 추측하지 마세요. "
                "날짜와 신청 기한은 원문 작성일 및 문맥을 함께 확인하도록 안내하세요. "
                "답변에서 근거 자료를 [자료 1] 형식으로 표시하세요."
            ),
            input=f"질문:\n{question}\n\n검색된 자료:\n{context_text}",
        )
        answer = response.output_text.strip()
        if not answer:
            raise RuntimeError("OpenAI가 빈 답변을 반환했습니다.")
        return answer
