from __future__ import annotations

import argparse

from backend.app.chunking import chunk_posts
from backend.app.config import get_settings
from backend.app.provider_factory import create_provider, effective_models, selected_provider_name
from backend.app.storage import load_posts
from backend.app.vector_store import ChromaVectorStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="수집 게시글을 임베딩해 Chroma에 저장합니다.")
    parser.add_argument("--chunk-size", type=int, default=900)
    parser.add_argument("--overlap", type=int, default=150)
    parser.add_argument("--reset", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    posts = load_posts(settings.raw_posts_path)
    chunks = chunk_posts(posts, chunk_size=args.chunk_size, overlap=args.overlap)
    provider = create_provider(settings)
    store = ChromaVectorStore(settings.chroma_path, settings.chroma_collection)
    if args.reset:
        store.reset()
    embeddings = provider.embed([chunk.text for chunk in chunks])
    store.upsert(chunks, embeddings)
    _, embedding_model = effective_models(settings)
    print(
        f"게시글 {len(posts)}건, 청크 {len(chunks)}개 인덱싱 완료 "
        f"(provider={selected_provider_name(settings)}, embedding={embedding_model})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
