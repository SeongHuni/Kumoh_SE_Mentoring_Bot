from threading import RLock

from fastapi import FastAPI

from rag_chatbot.config import Settings
from rag_chatbot.config import get_settings
from rag_chatbot.document_loader import load_knowledge_documents
from rag_chatbot.rag_service import RagService
from rag_chatbot.schemas import ChatRequest, ChatResponse, DocumentSummary, IndexResponse


def create_app(app_settings: Settings | None = None) -> FastAPI:
    settings = app_settings or get_settings()
    api = FastAPI(title=settings.app_name)
    service_cache: dict[str, RagService] = {}
    service_lock = RLock()

    def get_rag_service() -> RagService:
        with service_lock:
            if "service" not in service_cache:
                documents = load_knowledge_documents(settings.knowledge_dir)
                service_cache["service"] = RagService(
                    documents=documents,
                    top_k=settings.top_k,
                    chroma_dir=settings.chroma_dir,
                    collection_name=settings.collection_name,
                )
            return service_cache["service"]

    @api.get("/health")
    def health() -> dict[str, object]:
        documents = load_knowledge_documents(settings.knowledge_dir)
        return {"status": "ok", "documents": len(documents)}

    @api.post("/index/rebuild", response_model=IndexResponse)
    def rebuild_index() -> IndexResponse:
        with service_lock:
            service_cache.pop("service", None)
            stats = get_rag_service().rebuild_index()
            return IndexResponse(document_count=stats.document_count, chunk_count=stats.chunk_count)

    @api.get("/documents", response_model=list[DocumentSummary])
    def documents() -> list[DocumentSummary]:
        return [
            DocumentSummary(
                id=document.id,
                title=document.title,
                audience=document.audience,
                source_urls=document.source_urls,
                last_checked=document.last_checked,
                keywords=document.keywords,
            )
            for document in load_knowledge_documents(settings.knowledge_dir)
        ]

    @api.post("/chat", response_model=ChatResponse)
    def chat(request: ChatRequest) -> ChatResponse:
        with service_lock:
            return get_rag_service().answer(request.question)

    return api


app = create_app()
