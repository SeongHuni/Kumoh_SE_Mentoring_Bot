from __future__ import annotations

from functools import lru_cache

from chromadb.errors import ChromaError
from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from openai import APIError

from backend.app.config import get_settings
from backend.app.domain import BoardPost
from backend.app.index_manifest import IndexCompatibility, assess_index_compatibility
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


def get_vector_store() -> ChromaVectorStore:
    return ChromaVectorStore(settings.chroma_path, settings.chroma_collection)


@lru_cache(maxsize=4)
def get_topic_catalog(index_fingerprint: str) -> TopicCatalog:
    return load_topic_catalog(settings.topic_rules_path)


@lru_cache(maxsize=4)
def get_enriched_posts(index_fingerprint: str) -> list[BoardPost]:
    try:
        return enrich_posts(
            load_posts(settings.raw_posts_path),
            get_topic_catalog(index_fingerprint),
        )
    except FileNotFoundError:
        return []


@lru_cache(maxsize=4)
def get_rag_service(index_fingerprint: str) -> RAGService:
    provider = create_provider(settings)
    return RAGService(
        provider=provider,
        vector_store=get_vector_store(),
        top_k=settings.rag_top_k,
        min_score=settings.rag_min_score,
        topic_catalog=get_topic_catalog(index_fingerprint),
        posts=get_enriched_posts(index_fingerprint),
    )


def get_index_compatibility() -> IndexCompatibility:
    try:
        store = get_vector_store()
    except (OSError, ValueError, ChromaError):
        return IndexCompatibility(False, "index_unavailable", 0)
    return assess_index_compatibility(settings=settings, store=store)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"name": "SE Mentor Bot API", "docs": "/docs"}


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    compatibility = get_index_compatibility()
    provider_name = selected_provider_name(settings)
    chat_model, embedding_model = effective_models(settings)
    configured = provider_name == "local" or bool(settings.openai_api_key)
    if not configured:
        status = "needs_configuration"
    elif compatibility.reason == "index_unavailable":
        status = "unavailable"
    elif compatibility.reason == "empty_index":
        status = "needs_index"
    elif not compatibility.compatible:
        status = "needs_reindex"
    else:
        status = "ready"
    return HealthResponse(
        status=status,
        provider=provider_name,
        openai_configured=bool(settings.openai_api_key),
        indexed_chunks=compatibility.indexed_chunks,
        chat_model=chat_model,
        embedding_model=embedding_model,
        index_compatible=compatibility.compatible,
        index_reason=compatibility.reason,
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    if selected_provider_name(settings) == "openai" and not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="AI_PROVIDER=openai 설정에는 OPENAI_API_KEY가 필요합니다.",
        )

    compatibility = get_index_compatibility()
    if compatibility.reason == "index_unavailable":
        raise HTTPException(
            status_code=503,
            detail="인덱스 저장소 상태를 확인할 수 없습니다. 잠시 후 /api/health를 확인하세요.",
        )
    if compatibility.reason == "empty_index":
        raise HTTPException(
            status_code=409,
            detail=(
                "벡터 인덱스가 비어 있습니다. 인덱싱을 먼저 실행하세요: "
                "python -m backend.scripts.index --reset"
            ),
        )
    if not compatibility.compatible or compatibility.fingerprint is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "현재 설정 또는 데이터와 인덱스가 일치하지 않습니다. "
                "python -m backend.scripts.index --reset을 실행하세요."
            ),
        )
    try:
        service = get_rag_service(compatibility.fingerprint)
        return await run_in_threadpool(service.ask, payload.question)
    except APIError as exc:
        raise HTTPException(status_code=502, detail="OpenAI API 요청에 실패했습니다.") from exc
