from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from chromadb.errors import ChromaError
from openai import OpenAIError

from backend.app.chunking import chunk_posts
from backend.app.config import Settings, get_settings
from backend.app.index_manifest import (
    IndexManifest,
    build_index_manifest,
    build_index_signature,
    remove_index_manifest,
    write_index_manifest,
)
from backend.app.provider_factory import create_provider
from backend.app.storage import load_posts
from backend.app.topic_classifier import enrich_posts
from backend.app.topic_rules import load_topic_catalog
from backend.app.vector_store import ChromaVectorStore


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="수집 게시글을 임베딩해 Chroma에 저장합니다.")
    parser.add_argument("--chunk-size", type=int, default=None)
    parser.add_argument("--overlap", type=int, default=None)
    parser.add_argument("--reset", action="store_true")
    return parser.parse_args(argv)


def validate_cli_settings(args: argparse.Namespace, settings: Settings) -> None:
    if args.chunk_size is not None and args.chunk_size != settings.chunk_size:
        raise ValueError(
            "--chunk-size는 CHUNK_SIZE와 같아야 합니다. 환경 변수를 변경한 뒤 다시 실행하세요."
        )
    if args.overlap is not None and args.overlap != settings.chunk_overlap:
        raise ValueError(
            "--overlap은 CHUNK_OVERLAP과 같아야 합니다. 환경 변수를 변경한 뒤 다시 실행하세요."
        )


def validate_embedding_dimensions(
    embeddings: Sequence[Sequence[float]],
    *,
    expected_count: int,
    expected_dimensions: int,
) -> None:
    if len(embeddings) != expected_count:
        raise ValueError(
            f"임베딩 수가 청크 수와 일치하지 않습니다: {len(embeddings)} != {expected_count}"
        )
    for index, embedding in enumerate(embeddings):
        if len(embedding) != expected_dimensions:
            raise ValueError(
                "임베딩 차원이 EMBEDDING_DIMENSIONS와 일치하지 않습니다: "
                f"청크 {index}, {len(embedding)} != {expected_dimensions}"
            )


def run_index(args: argparse.Namespace) -> IndexManifest:
    settings = get_settings()
    validate_cli_settings(args, settings)
    signature_before = build_index_signature(settings)

    catalog = load_topic_catalog(settings.topic_rules_path)
    posts = enrich_posts(load_posts(settings.raw_posts_path), catalog)
    chunks = chunk_posts(
        posts,
        chunk_size=settings.chunk_size,
        overlap=settings.chunk_overlap,
    )
    if not chunks:
        raise ValueError("인덱싱할 청크가 없습니다.")

    store = ChromaVectorStore(settings.chroma_path, settings.chroma_collection)
    if store.count() > 0 and not args.reset:
        raise ValueError(
            "기존 인덱스가 있습니다. python -m backend.scripts.index --reset을 실행하세요."
        )

    provider = create_provider(settings)
    embeddings = provider.embed([chunk.text for chunk in chunks])
    validate_embedding_dimensions(
        embeddings,
        expected_count=len(chunks),
        expected_dimensions=settings.embedding_dimensions,
    )

    signature_after = build_index_signature(settings)
    if signature_after != signature_before:
        raise ValueError("인덱싱 중 원본 또는 설정이 변경되었습니다. 다시 실행하세요.")

    remove_index_manifest(settings.chroma_path)
    if args.reset:
        store.reset()
    store.upsert(chunks, embeddings)
    indexed_chunks = store.count()
    if indexed_chunks != len(chunks):
        raise RuntimeError(
            "저장된 청크 수가 생성한 청크 수와 일치하지 않습니다: "
            f"{indexed_chunks} != {len(chunks)}"
        )

    manifest = build_index_manifest(signature_after, indexed_chunks=indexed_chunks)
    write_index_manifest(settings.chroma_path, manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = run_index(args)
    except (OSError, ValueError, RuntimeError, OpenAIError, ChromaError) as exc:
        print(f"인덱싱 오류: {exc}", file=sys.stderr)
        return 2

    print(
        f"청크 {manifest.indexed_chunks}개 인덱싱 완료 "
        f"(provider={manifest.provider}, embedding={manifest.embedding_model}, "
        f"fingerprint={manifest.fingerprint[:12]})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
