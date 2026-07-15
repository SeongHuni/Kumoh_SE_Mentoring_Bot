from dataclasses import replace

import pytest
from backend.app.config import get_settings
from backend.app.domain import TextChunk
from backend.app.index_manifest import build_index_signature as real_build_index_signature
from backend.scripts import index
from chromadb.errors import InternalError


def make_chunk() -> TextChunk:
    return TextChunk(
        id="kumoh:1:0",
        post_id="1",
        source="kumoh",
        title="테스트 공지",
        text="테스트 공지 본문",
        url="https://example.com/1",
        published_at="2026-07-15",
        chunk_index=0,
        topic_key="general",
        topic_label="전체 공지",
        is_latest_topic=True,
    )


class FakeProvider:
    def __init__(self, harness, embeddings, error):
        self.harness = harness
        self.embeddings = embeddings
        self.error = error
        self.embed_calls = 0

    def embed(self, texts):
        self.embed_calls += 1
        self.harness.events.append("embed")
        if self.error:
            raise self.error
        return self.embeddings


class FakeStore:
    def __init__(self, harness, count, upsert_error, post_upsert_count):
        self.harness = harness
        self.value = count
        self.upsert_error = upsert_error
        self.post_upsert_count = post_upsert_count
        self.reset_calls = 0
        self.upserted = False
        self.count_after_recorded = False

    def count(self):
        if self.upserted and not self.count_after_recorded:
            self.harness.events.append("count_after")
            self.count_after_recorded = True
        return self.value

    def reset(self):
        self.harness.events.append("reset")
        self.reset_calls += 1
        self.value = 0

    def upsert(self, chunks, embeddings):
        self.harness.events.append("upsert")
        if self.upsert_error:
            raise self.upsert_error
        self.value = len(chunks) if self.post_upsert_count is None else self.post_upsert_count
        self.upserted = True


class Harness:
    def __init__(
        self,
        tmp_path,
        existing_count,
        dimensions,
        embeddings,
        provider_error,
        upsert_error,
        post_upsert_count,
        chunks,
    ):
        raw_posts_path = tmp_path / "posts.json"
        topic_rules_path = tmp_path / "topic-rules.json"
        raw_posts_path.write_bytes(b"[]")
        topic_rules_path.write_bytes(b"{}")
        self.settings = replace(
            get_settings(),
            ai_provider="local",
            openai_api_key=None,
            chroma_path=tmp_path / "chroma",
            chroma_collection="test-posts",
            raw_posts_path=raw_posts_path,
            topic_rules_path=topic_rules_path,
            embedding_dimensions=dimensions,
            chunk_size=900,
            chunk_overlap=150,
        )
        self.events = []
        self.chunks = [make_chunk()] if chunks is None else chunks
        self.manifest_removed = False
        self.manifest_written = False
        self.written_manifest = None
        self.changed_inputs = False
        self.signature_calls = 0
        vectors = embeddings
        if vectors is None:
            vectors = [[0.0] * dimensions for _ in self.chunks]
        self.provider = FakeProvider(self, vectors, provider_error)
        self.store = FakeStore(self, existing_count, upsert_error, post_upsert_count)


def install_harness(
    monkeypatch,
    tmp_path,
    *,
    existing_count,
    dimensions=256,
    embeddings=None,
    provider_error=None,
    upsert_error=None,
    post_upsert_count=None,
    changed_inputs=False,
    chunks=None,
):
    harness = Harness(
        tmp_path,
        existing_count,
        dimensions,
        embeddings,
        provider_error,
        upsert_error,
        post_upsert_count,
        chunks,
    )
    harness.changed_inputs = changed_inputs

    def signature(settings):
        harness.signature_calls += 1
        value = real_build_index_signature(settings)
        if harness.changed_inputs and harness.signature_calls == 2:
            return value.model_copy(update={"raw_posts_sha256": "f" * 64})
        return value

    def remove_manifest(chroma_path):
        harness.events.append("remove_manifest")
        harness.manifest_removed = True

    def write_manifest(chroma_path, manifest):
        harness.events.append("write_manifest")
        harness.manifest_written = True
        harness.written_manifest = manifest
        return chroma_path / "index-manifest.json"

    monkeypatch.setattr(index, "get_settings", lambda: harness.settings)
    monkeypatch.setattr(index, "load_topic_catalog", lambda path: object())
    monkeypatch.setattr(index, "load_posts", lambda path: [object()])
    monkeypatch.setattr(index, "enrich_posts", lambda posts, catalog: posts)
    monkeypatch.setattr(
        index,
        "chunk_posts",
        lambda posts, chunk_size, overlap: harness.chunks,
    )
    monkeypatch.setattr(index, "ChromaVectorStore", lambda path, name: harness.store)
    monkeypatch.setattr(index, "create_provider", lambda settings: harness.provider)
    monkeypatch.setattr(index, "build_index_signature", signature, raising=False)
    monkeypatch.setattr(index, "remove_index_manifest", remove_manifest, raising=False)
    monkeypatch.setattr(index, "write_index_manifest", write_manifest, raising=False)
    return harness


def test_parse_args_accepts_explicit_argv() -> None:
    args = index.parse_args(["--reset", "--chunk-size", "900", "--overlap", "150"])

    assert args.reset is True
    assert args.chunk_size == 900
    assert args.overlap == 150


def test_nonempty_index_requires_reset(monkeypatch, tmp_path, capsys) -> None:
    harness = install_harness(monkeypatch, tmp_path, existing_count=3)

    assert index.main([]) == 2

    assert "--reset" in capsys.readouterr().err
    assert harness.provider.embed_calls == 0
    assert harness.store.reset_calls == 0
    assert harness.manifest_removed is False


@pytest.mark.parametrize(
    ("arguments", "message"),
    [(["--chunk-size", "901"], "CHUNK_SIZE"), (["--overlap", "151"], "CHUNK_OVERLAP")],
)
def test_cli_chunk_override_must_match_settings(
    monkeypatch, tmp_path, capsys, arguments, message
) -> None:
    harness = install_harness(monkeypatch, tmp_path, existing_count=0)

    assert index.main(arguments) == 2

    assert message in capsys.readouterr().err
    assert harness.events == []


def test_empty_chunks_fail_before_provider(monkeypatch, tmp_path, capsys) -> None:
    harness = install_harness(monkeypatch, tmp_path, existing_count=0, chunks=[])

    assert index.main([]) == 2

    assert "청크" in capsys.readouterr().err
    assert harness.provider.embed_calls == 0
    assert harness.manifest_removed is False


def test_provider_failure_preserves_existing_index(monkeypatch, tmp_path) -> None:
    harness = install_harness(
        monkeypatch,
        tmp_path,
        existing_count=3,
        provider_error=RuntimeError("provider failed"),
    )

    assert index.main(["--reset"]) == 2

    assert harness.events == ["embed"]
    assert harness.store.reset_calls == 0
    assert harness.manifest_removed is False


def test_embedding_dimension_mismatch_preserves_existing_index(monkeypatch, tmp_path) -> None:
    harness = install_harness(
        monkeypatch,
        tmp_path,
        existing_count=3,
        dimensions=256,
        embeddings=[[0.0] * 255],
    )

    assert index.main(["--reset"]) == 2

    assert harness.store.reset_calls == 0
    assert harness.manifest_removed is False


def test_input_change_during_embedding_aborts_before_reset(monkeypatch, tmp_path) -> None:
    harness = install_harness(
        monkeypatch,
        tmp_path,
        existing_count=3,
        changed_inputs=True,
    )

    assert index.main(["--reset"]) == 2

    assert harness.events == ["embed"]
    assert harness.store.reset_calls == 0
    assert harness.manifest_removed is False


def test_failed_upsert_leaves_manifest_invalidated(monkeypatch, tmp_path) -> None:
    harness = install_harness(
        monkeypatch,
        tmp_path,
        existing_count=3,
        upsert_error=InternalError("upsert failed"),
    )

    assert index.main(["--reset"]) == 2

    assert harness.events == ["embed", "remove_manifest", "reset", "upsert"]
    assert harness.manifest_removed is True
    assert harness.manifest_written is False


def test_stored_chunk_count_mismatch_does_not_write_manifest(monkeypatch, tmp_path) -> None:
    harness = install_harness(
        monkeypatch,
        tmp_path,
        existing_count=3,
        post_upsert_count=2,
    )

    assert index.main(["--reset"]) == 2

    assert harness.events[-1] == "count_after"
    assert harness.manifest_removed is True
    assert harness.manifest_written is False


def test_success_writes_manifest_after_verified_count(
    monkeypatch, tmp_path, capsys
) -> None:
    harness = install_harness(monkeypatch, tmp_path, existing_count=3)

    assert index.main(["--reset"]) == 0

    assert harness.events == [
        "embed",
        "remove_manifest",
        "reset",
        "upsert",
        "count_after",
        "write_manifest",
    ]
    assert harness.written_manifest.indexed_chunks == 1
    assert harness.written_manifest.fingerprint[:12] in capsys.readouterr().out
