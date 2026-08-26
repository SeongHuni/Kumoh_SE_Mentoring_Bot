from __future__ import annotations

import time
from functools import lru_cache

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from openai import APIError

from backend.app.config import get_settings
from backend.app.domain import BoardPost
from backend.app.provider_factory import create_provider, effective_models, selected_provider_name
from backend.app.ranking import load_scoring_config
from backend.app.rag import RAGService
from backend.app.session import Session
from backend.app.schemas import ApiError, ChatRequest, ChatResponse, HealthResponse
from backend.app.storage import load_posts
from backend.app.topic_classifier import enrich_posts
from backend.app.topic_rules import TopicCatalog, load_topic_catalog
from backend.app.vector_store import ChromaVectorStore

settings = get_settings()
app = FastAPI(
    title="SE Mentor Bot API",
    version="0.1.0",
    summary="금오공과대학교 소프트웨어전공 공지 기반 RAG 챗봇 API",
    description=(
        "공개 학과 게시글과 SE 게시판을 검색해 답변하고, "
        "답변에 사용한 원문 게시글을 함께 반환합니다."
    ),
    openapi_tags=[
        {"name": "System", "description": "서비스와 인덱스의 준비 상태를 확인합니다."},
        {"name": "Chat", "description": "검색 근거와 함께 챗봇 답변을 생성합니다."},
    ],
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
    return ChromaVectorStore(settings.chroma_path, settings.chroma_collection, settings.chroma_url)


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
        scoring=load_scoring_config(settings.importance_path),
    )


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"name": "SE Mentor Bot API", "docs": "/docs"}


@app.get(
    "/api/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="서비스 상태 확인",
)
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
        collection=settings.chroma_collection,
        chat_model=chat_model,
        embedding_model=embedding_model,
    )


# ---------------------------------------------------------------- 세션
# 프론트가 session_id 를 보내면 그것으로, 안 보내면 클라이언트 주소로 구분한다.
# 주소 기준은 시연·단일 사용자 환경에서만 안전하다. 같은 망에 여러 명이 있으면
# 이력이 섞이므로, 다중 사용자로 갈 때는 프론트가 session_id 를 보내야 한다.
_sessions: dict[str, tuple[Session, float]] = {}


def _session_key(payload: ChatRequest, request: Request) -> str:
    if payload.session_id:
        return f"sid:{payload.session_id}"
    client = request.client.host if request.client else "local"
    return f"ip:{client}"


def _get_session(key: str) -> Session:
    now = time.monotonic()
    ttl = settings.session_ttl_seconds
    for stale in [k for k, (_, touched) in _sessions.items() if now - touched > ttl]:
        _sessions.pop(stale, None)
    session, _ = _sessions.get(key, (Session(), now))
    _sessions[key] = (session, now)
    return session


@app.post(
    "/api/chat",
    response_model=ChatResponse,
    tags=["Chat"],
    summary="게시글 근거 기반 답변 생성",
    responses={
        409: {"model": ApiError, "description": "검색 인덱스가 비어 있습니다."},
        502: {"model": ApiError, "description": "OpenAI 요청에 실패했습니다."},
    },
)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    if get_vector_store().count() == 0:
        raise HTTPException(
            status_code=409,
            detail="벡터 인덱스가 비어 있습니다. 인덱싱을 먼저 실행하세요.",
        )
    session = _get_session(_session_key(payload, request))
    try:
        return await run_in_threadpool(
            get_rag_service().ask,
            payload.question,
            session,
            payload.confirmed_intent_key,
        )
    except APIError as exc:
        raise HTTPException(status_code=502, detail="OpenAI API 요청에 실패했습니다.") from exc
