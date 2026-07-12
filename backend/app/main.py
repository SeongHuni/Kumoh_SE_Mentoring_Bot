from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from openai import APIError

from backend.app.config import get_settings
from backend.app.domain import BoardPost
from backend.app.provider_factory import create_provider, effective_models, selected_provider_name
from backend.app.rag import RAGService
from backend.app.schemas import ChatRequest, ChatResponse, HealthResponse
from backend.app.storage import load_posts
from backend.app.topic_classifier import enrich_posts
from backend.app.topic_rules import TopicCatalog, load_topic_catalog
from backend.app.vector_store import ChromaVectorStore

settings = get_settings()
app = FastAPI(
    title="SE Mentor Bot API",
    version="0.1.0",
    description="공개 학과 게시글을 근거로 답변하는 RAG 챗봇 API",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@lru_cache(maxsize=1)
def get_vector_store() -> ChromaVectorStore:
    return ChromaVectorStore(settings.chroma_path, settings.chroma_collection)


@lru_cache(maxsize=1)
def get_topic_catalog() -> TopicCatalog:
    return load_topic_catalog(settings.topic_rules_path)


@lru_cache(maxsize=1)
def get_enriched_posts() -> list[BoardPost]:
    try:
        return enrich_posts(load_posts(settings.raw_posts_path), get_topic_catalog())
    except FileNotFoundError:
        return []


@lru_cache(maxsize=1)
def get_rag_service() -> RAGService:
    provider = create_provider(settings)
    return RAGService(
        provider=provider,
        vector_store=get_vector_store(),
        top_k=settings.rag_top_k,
        min_score=settings.rag_min_score,
        topic_catalog=get_topic_catalog(),
        posts=get_enriched_posts(),
    )


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"name": "SE Mentor Bot API", "docs": "/docs"}


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    try:
        count = get_vector_store().count()
    except Exception:
        count = 0
    provider_name = selected_provider_name(settings)
    chat_model, embedding_model = effective_models(settings)
    configured = provider_name == "local" or bool(settings.openai_api_key)
    status = "ready" if configured and count else "needs_index"
    return HealthResponse(
        status=status,
        provider=provider_name,
        openai_configured=configured,
        indexed_chunks=count,
        chat_model=chat_model,
        embedding_model=embedding_model,
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    if get_vector_store().count() == 0:
        raise HTTPException(
            status_code=409,
            detail="벡터 인덱스가 비어 있습니다. 인덱싱을 먼저 실행하세요.",
        )
    try:
        return await run_in_threadpool(get_rag_service().ask, payload.question)
    except APIError as exc:
        raise HTTPException(status_code=502, detail="OpenAI API 요청에 실패했습니다.") from exc
