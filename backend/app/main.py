from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from openai import APIConnectionError, APIError, AuthenticationError

from backend.app.chroma_store import ChromaDataStore, ChromaStoreError
from backend.app.config import get_settings
from backend.app.rag import RAGService
from backend.app.schemas import ChatRequest, ChatResponse, HealthResponse, LiveResponse

settings = get_settings()
app = FastAPI(title="SE Mentor Bot API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def get_store() -> ChromaDataStore:
    return ChromaDataStore(get_settings())


def get_rag_service() -> RAGService:
    return RAGService(get_settings(), get_store())


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"name": "SE Mentor Bot API", "docs": "/docs"}


@app.get("/api/live", response_model=LiveResponse)
def live() -> LiveResponse:
    return LiveResponse()


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    current = get_settings()
    try:
        index = get_store().inspect()
    except ChromaStoreError:
        return HealthResponse(
            status="unavailable",
            collection=current.chroma_collection,
            indexed_chunks=0,
            embedding_model=current.embedding_model,
            answer_model=current.answer_model,
            chunk_size_tokens=current.chunk_size_tokens,
            chunk_overlap_tokens=current.chunk_overlap_tokens,
            embedding_api_configured=bool(current.embedding_api_key),
            answer_api_configured=bool(current.answer_api_key),
            index_compatible=False,
            index_reason="collection_unavailable",
        )

    if not current.api_keys_configured:
        status = "needs_configuration"
    elif index.count == 0:
        status = "needs_index"
    elif not index.compatible:
        status = "needs_reindex"
    else:
        status = "ready"
    return HealthResponse(
        status=status,
        collection=current.chroma_collection,
        indexed_chunks=index.count,
        embedding_model=current.embedding_model,
        answer_model=current.answer_model,
        chunk_size_tokens=current.chunk_size_tokens,
        chunk_overlap_tokens=current.chunk_overlap_tokens,
        embedding_api_configured=bool(current.embedding_api_key),
        answer_api_configured=bool(current.answer_api_key),
        index_compatible=index.compatible,
        index_reason=index.reason,
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    current = get_settings()
    if not current.api_keys_configured:
        raise HTTPException(
            status_code=503,
            detail="EMBEDDING_API_KEY와 ANSWER_API_KEY를 환경 변수에 설정해 주세요.",
        )
    try:
        index = get_store().inspect()
    except ChromaStoreError as exc:
        raise HTTPException(status_code=503, detail="Chroma 데이터를 열 수 없습니다.") from exc
    if index.count == 0:
        raise HTTPException(status_code=409, detail="Chroma 컬렉션이 비어 있습니다.")
    if not index.compatible:
        raise HTTPException(
            status_code=409,
            detail="Chroma 컬렉션 설정이 현재 임베딩·청킹 설정과 일치하지 않습니다.",
        )
    try:
        service = get_rag_service()
        return await run_in_threadpool(service.ask, payload.question)
    except AuthenticationError as exc:
        raise HTTPException(status_code=502, detail="AI API 키 인증에 실패했습니다.") from exc
    except (APIConnectionError, APIError) as exc:
        raise HTTPException(status_code=502, detail="AI API 요청에 실패했습니다.") from exc
    except ChromaStoreError as exc:
        raise HTTPException(status_code=503, detail="Chroma 검색에 실패했습니다.") from exc
