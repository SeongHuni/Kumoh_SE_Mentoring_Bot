from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)


class Source(BaseModel):
    id: str
    title: str
    source_urls: list[str]
    last_checked: str
    score: float
    chunk_id: str | None = None
    excerpt: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]


class IndexResponse(BaseModel):
    document_count: int
    chunk_count: int


class DocumentSummary(BaseModel):
    id: str
    title: str
    audience: str
    source_urls: list[str]
    last_checked: str
    keywords: list[str]
