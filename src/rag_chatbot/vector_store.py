from collections import Counter
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import re

import chromadb

from rag_chatbot.document_loader import KnowledgeDocument


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9가-힣]+")


def tokenize(text: str) -> list[str]:
    tokens = [token.lower() for token in TOKEN_PATTERN.findall(text)]
    expanded: list[str] = []

    for token in tokens:
        expanded.append(token)
        if re.search(r"[가-힣]", token) and len(token) >= 3:
            max_ngram = min(6, len(token))
            for size in range(2, max_ngram + 1):
                expanded.extend(token[start : start + size] for start in range(len(token) - size + 1))

    return expanded


def lexical_similarity(query: str, text: str) -> float:
    query_tokens = set(tokenize(query))
    text_tokens = set(tokenize(text))
    if not query_tokens or not text_tokens:
        return 0.0
    return len(query_tokens & text_tokens) / math.sqrt(len(query_tokens) * len(text_tokens))


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    document: KnowledgeDocument
    chunk_index: int
    text: str


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: DocumentChunk
    score: float

    @property
    def document(self) -> KnowledgeDocument:
        return self.chunk.document


@dataclass(frozen=True)
class IndexStats:
    document_count: int
    chunk_count: int


def chunk_document(
    document: KnowledgeDocument,
    max_chars: int = 900,
    overlap: int = 150,
) -> list[DocumentChunk]:
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than 0.")
    if overlap < 0:
        raise ValueError("overlap must be 0 or greater.")

    source_text = "\n".join(
        [
            document.title,
            f"대상: {document.audience}",
            f"키워드: {', '.join(document.keywords)}",
            document.body,
        ]
    ).strip()
    if not source_text:
        return []

    step = max(1, max_chars - overlap)
    chunks: list[DocumentChunk] = []
    start = 0

    while start < len(source_text):
        text = source_text[start : start + max_chars].strip()
        if text:
            chunk_index = len(chunks)
            chunks.append(
                DocumentChunk(
                    chunk_id=f"{document.id}:{chunk_index}",
                    document=document,
                    chunk_index=chunk_index,
                    text=text,
                )
            )
        start += step

    return chunks


class HashEmbeddingFunction:
    """Deterministic local embeddings for API-key-free RAG setup verification."""

    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in tokenize(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, byteorder="big", signed=False)
            index = value % self.dimensions
            vector[index] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class LocalKnowledgeIndex:
    """Small deterministic index for local development and tests."""

    def __init__(self, documents: list[KnowledgeDocument]):
        self.documents = documents
        self.document_vectors = [self._vectorize_document(document) for document in documents]

    def _vectorize_document(self, document: KnowledgeDocument) -> Counter[str]:
        weighted_text = " ".join(
            [
                document.title,
                " ".join(document.keywords) * 3,
                document.audience,
                document.body,
            ]
        )
        return Counter(tokenize(weighted_text))

    @staticmethod
    def _cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
        common = set(left) & set(right)
        numerator = sum(left[token] * right[token] for token in common)
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)

    def search(self, query: str, top_k: int) -> list[tuple[KnowledgeDocument, float]]:
        query_vector = Counter(tokenize(query))
        scored = [
            (document, self._cosine_similarity(query_vector, vector))
            for document, vector in zip(self.documents, self.document_vectors, strict=True)
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        return [(document, score) for document, score in scored[:top_k] if score > 0]


class ChromaKnowledgeIndex:
    def __init__(
        self,
        documents: list[KnowledgeDocument],
        persist_directory: Path,
        collection_name: str,
        embedding_function: HashEmbeddingFunction | None = None,
        max_chunk_chars: int = 900,
        chunk_overlap: int = 150,
    ):
        self.documents = documents
        self.persist_directory = persist_directory.expanduser().resolve()
        self.collection_name = collection_name
        self.embedding_function = embedding_function or HashEmbeddingFunction()
        self.max_chunk_chars = max_chunk_chars
        self.chunk_overlap = chunk_overlap
        self.chunks_by_id: dict[str, DocumentChunk] = {}
        self.client = chromadb.PersistentClient(path=str(self.persist_directory))

    def rebuild(self) -> IndexStats:
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self._delete_collection_if_exists()
        collection = self.client.create_collection(name=self.collection_name)
        chunks = [
            chunk
            for document in self.documents
            for chunk in chunk_document(document, self.max_chunk_chars, self.chunk_overlap)
        ]
        self.chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}

        if chunks:
            collection.add(
                ids=[chunk.chunk_id for chunk in chunks],
                documents=[chunk.text for chunk in chunks],
                embeddings=self.embedding_function.embed([chunk.text for chunk in chunks]),
                metadatas=[
                    {
                        "document_id": chunk.document.id,
                        "title": chunk.document.title,
                        "chunk_index": chunk.chunk_index,
                        "source_urls": " | ".join(chunk.document.source_urls),
                        "last_checked": chunk.document.last_checked,
                    }
                    for chunk in chunks
                ],
            )

        return IndexStats(document_count=len(self.documents), chunk_count=len(chunks))

    def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        collection = self.client.get_or_create_collection(name=self.collection_name)
        if not self.chunks_by_id:
            self._hydrate_chunks_from_documents()
        collection_count = collection.count()
        if collection_count == 0:
            return []

        result = collection.query(
            query_embeddings=self.embedding_function.embed([query]),
            n_results=min(collection_count, max(1, top_k * 4)),
        )
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]

        retrieved: list[RetrievedChunk] = []
        for chunk_id, distance in zip(ids, distances, strict=False):
            chunk = self.chunks_by_id.get(chunk_id)
            if not chunk:
                continue
            vector_score = 1.0 / (1.0 + float(distance))
            lexical_score = lexical_similarity(query, chunk.text)
            retrieved.append(
                RetrievedChunk(
                    chunk=chunk,
                    score=round((vector_score * 0.65) + (lexical_score * 0.35), 4),
                )
            )

        retrieved.sort(key=lambda item: item.score, reverse=True)
        return retrieved[:top_k]

    def _delete_collection_if_exists(self) -> None:
        try:
            self.client.delete_collection(name=self.collection_name)
        except Exception:
            return

    def _hydrate_chunks_from_documents(self) -> None:
        chunks = [
            chunk
            for document in self.documents
            for chunk in chunk_document(document, self.max_chunk_chars, self.chunk_overlap)
        ]
        self.chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
