from __future__ import annotations

from collections.abc import Sequence

from openai import OpenAI

from backend.app.chroma_store import RetrievedDocument
from backend.app.config import Settings


def format_as_bullets(answer: str) -> str:
    bullets: list[str] = []
    for line in answer.splitlines():
        text = line.strip()
        if not text:
            continue
        if text.startswith("- "):
            bullets.append(text)
            continue
        normalized = text.lstrip("-*• ").strip()
        if normalized:
            bullets.append(f"- {normalized}")
    return "\n".join(bullets)


class OpenAIRagClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.embedding_api_key or not settings.answer_api_key:
            raise ValueError("Embedding and answer API keys are required.")
        self.embedding_client = OpenAI(api_key=settings.embedding_api_key)
        self.answer_client = OpenAI(api_key=settings.answer_api_key)
        self.settings = settings

    def embed_query(self, question: str) -> list[float]:
        response = self.embedding_client.embeddings.create(
            model=self.settings.embedding_model,
            input=question,
            dimensions=self.settings.embedding_dimensions,
            encoding_format="float",
        )
        if not response.data or not response.data[0].embedding:
            raise RuntimeError("Embedding API returned no vector.")
        return list(response.data[0].embedding)

    def answer(self, question: str, documents: Sequence[RetrievedDocument]) -> str:
        context = "\n\n".join(
            f"[자료 {index}]\n제목: {item.source.title}\n"
            f"게시일: {item.source.published_at or '알 수 없음'}\n"
            f"내용:\n{item.text}"
            for index, item in enumerate(documents, start=1)
        )
        response = self.answer_client.responses.create(
            model=self.settings.answer_model,
            store=False,
            temperature=self.settings.answer_temperature,
            max_output_tokens=700,
            instructions=(
                "당신은 금오공과대학교 소프트웨어공학과 안내 도우미입니다. "
                "반드시 제공된 자료에 근거해서만 한국어로 답하세요. "
                "자료에 없는 사실은 추측하지 말고 모른다고 말하세요. "
                "답변은 제목이나 서술형 문단 없이 반드시 개조식으로 작성하세요. "
                "첫 줄부터 '- '로 시작하는 짧은 3~6개 항목으로 답하고, "
                "각 항목에는 하나의 사실만 담으세요. "
                "근거를 사용한 항목에는 [자료 1]처럼 자료 번호를 붙이세요."
            ),
            input=f"질문:\n{question}\n\n검색 자료:\n{context}",
        )
        answer = response.output_text.strip()
        if not answer:
            raise RuntimeError("Answer API returned an empty response.")
        return format_as_bullets(answer)
