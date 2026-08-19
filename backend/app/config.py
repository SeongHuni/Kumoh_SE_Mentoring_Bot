from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPOSITORY_ROOT / ".env")


def _first_nonempty(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return None


CHROMA_PATH = REPOSITORY_ROOT / "chroma-data"
CHROMA_COLLECTION = "sw_notice_d500"
EMBEDDING_DIMENSIONS = 1536
CHUNK_SIZE_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 0
RAG_TOP_K = 5
CATEGORY_PROBE_K = 20


@dataclass(frozen=True)
class Settings:
    embedding_api_key: str | None
    answer_api_key: str | None
    embedding_model: str
    answer_model: str
    chroma_path: Path = CHROMA_PATH
    chroma_collection: str = CHROMA_COLLECTION
    embedding_dimensions: int = EMBEDDING_DIMENSIONS
    chunk_size_tokens: int = CHUNK_SIZE_TOKENS
    chunk_overlap_tokens: int = CHUNK_OVERLAP_TOKENS
    top_k: int = RAG_TOP_K
    category_probe_k: int = CATEGORY_PROBE_K

    @property
    def api_keys_configured(self) -> bool:
        return bool(self.embedding_api_key and self.answer_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        embedding_api_key=_first_nonempty("EMBEDDING_API_KEY"),
        answer_api_key=_first_nonempty("ANSWER_API_KEY"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small").strip(),
        answer_model=os.getenv("ANSWER_MODEL", "gpt-4.1-mini").strip(),
    )
