from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Department RAG Chatbot"
    knowledge_dir: Path = Path("data/knowledge")
    chroma_dir: Path = Path("data/chroma")
    collection_name: str = "department_knowledge"
    top_k: int = 4

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()

