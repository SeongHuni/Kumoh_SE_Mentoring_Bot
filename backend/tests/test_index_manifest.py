import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from backend.app import index_manifest
from backend.app.config import get_settings
from backend.app.index_manifest import (
    IndexCompatibility,
    assess_index_compatibility,
    build_index_manifest,
    build_index_signature,
    index_manifest_path,
    read_index_manifest,
    remove_index_manifest,
    sha256_file,
    write_index_manifest,
)
from backend.app.local_service import LocalHashProvider
from pydantic import ValidationError

FIXED_TIME = datetime(2026, 7, 15, 3, 0, tzinfo=UTC)
LATER_TIME = datetime(2026, 7, 15, 4, 0, tzinfo=UTC)


def make_settings(tmp_path):
    raw_posts_path = tmp_path / "posts.json"
    topic_rules_path = tmp_path / "topic-rules.json"
    raw_posts_path.write_bytes(b"[]")
    topic_rules_path.write_bytes(b"{}")
    return replace(
        get_settings(),
        ai_provider="local",
        openai_api_key=None,
        chroma_path=tmp_path / "chroma",
        chroma_collection="test-posts",
        raw_posts_path=raw_posts_path,
        topic_rules_path=topic_rules_path,
        embedding_dimensions=256,
        chunk_size=900,
        chunk_overlap=150,
    )


def make_manifest(tmp_path, indexed_chunks=3):
    signature = build_index_signature(make_settings(tmp_path))
    return build_index_manifest(signature, indexed_chunks=indexed_chunks, now=FIXED_TIME)


class FakeStore:
    def __init__(self, count=3, error=None):
        self.value = count
        self.error = error

    def count(self):
        if self.error:
            raise self.error
        return self.value


def arrange_case(tmp_path, setup):
    settings = make_settings(tmp_path)
    if setup == "unavailable":
        return settings, FakeStore(error=RuntimeError("unavailable"))
    if setup == "empty":
        return settings, FakeStore(count=0)
    if setup == "missing":
        return settings, FakeStore(count=3)
    if setup == "invalid":
        settings.chroma_path.mkdir(parents=True)
        index_manifest_path(settings.chroma_path).write_text("{invalid", encoding="utf-8")
        return settings, FakeStore(count=3)

    signature = build_index_signature(settings)
    manifest = build_index_manifest(signature, indexed_chunks=3, now=FIXED_TIME)
    write_index_manifest(settings.chroma_path, manifest)
    store = FakeStore(count=3)
    if setup == "settings":
        settings = replace(settings, embedding_dimensions=384)
    elif setup == "content":
        settings.raw_posts_path.write_bytes(b"[ ]")
    elif setup == "content_unavailable":
        settings.raw_posts_path.unlink()
    elif setup == "count":
        store.value = 2
    return settings, store


def test_file_hash_changes_for_byte_only_format_change(tmp_path) -> None:
    path = tmp_path / "input.json"
    path.write_bytes(b'{"a":1}')
    first = sha256_file(path)

    path.write_bytes(b'{ "a": 1 }')

    assert first == hashlib.sha256(b'{"a":1}').hexdigest()
    assert sha256_file(path) != first


def test_signature_uses_effective_local_model_and_input_hashes(tmp_path) -> None:
    settings = make_settings(tmp_path)

    signature = build_index_signature(settings)

    assert signature.provider == "local"
    assert signature.embedding_model == LocalHashProvider.embedding_model
    assert signature.raw_posts_sha256 == sha256_file(settings.raw_posts_path)
    assert signature.topic_rules_sha256 == sha256_file(settings.topic_rules_path)


def test_signature_fingerprint_is_deterministic_and_ignores_evidence_fields(tmp_path) -> None:
    settings = make_settings(tmp_path)
    signature = build_index_signature(settings)

    first = build_index_manifest(signature, indexed_chunks=3, now=FIXED_TIME)
    second = build_index_manifest(signature, indexed_chunks=9, now=LATER_TIME)

    assert first.fingerprint == second.fingerprint
    assert len(first.fingerprint) == 64


def test_manifest_round_trip_is_atomic_and_strict(tmp_path) -> None:
    manifest = make_manifest(tmp_path, indexed_chunks=3)

    path = write_index_manifest(tmp_path / "chroma", manifest)

    assert path == index_manifest_path(tmp_path / "chroma")
    assert read_index_manifest(tmp_path / "chroma") == manifest
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert set(payload) == {
        "schema_version",
        "collection",
        "provider",
        "embedding_model",
        "embedding_dimensions",
        "chunk_size",
        "chunk_overlap",
        "raw_posts_sha256",
        "topic_rules_sha256",
        "indexed_chunks",
        "generated_at",
        "fingerprint",
    }

    payload["unexpected"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValidationError):
        read_index_manifest(tmp_path / "chroma")


def test_manifest_rejects_tampered_fingerprint(tmp_path) -> None:
    manifest = make_manifest(tmp_path, indexed_chunks=3)
    path = write_index_manifest(tmp_path / "chroma", manifest)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["chunk_size"] = 901
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValidationError, match="fingerprint"):
        read_index_manifest(tmp_path / "chroma")


def test_atomic_writer_removes_temporary_file_when_replace_fails(
    monkeypatch, tmp_path
) -> None:
    manifest = make_manifest(tmp_path)
    monkeypatch.setattr(
        index_manifest.os,
        "replace",
        Mock(side_effect=OSError("replace failed")),
    )

    with pytest.raises(OSError, match="replace failed"):
        write_index_manifest(tmp_path / "chroma", manifest)

    assert not index_manifest_path(tmp_path / "chroma").exists()
    assert not list((tmp_path / "chroma").glob("*.tmp"))


def test_remove_manifest_is_idempotent(tmp_path) -> None:
    manifest = make_manifest(tmp_path)
    path = write_index_manifest(tmp_path / "chroma", manifest)

    remove_index_manifest(tmp_path / "chroma")
    remove_index_manifest(tmp_path / "chroma")

    assert not path.exists()


@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        ("unavailable", "index_unavailable"),
        ("empty", "empty_index"),
        ("missing", "missing_manifest"),
        ("invalid", "invalid_manifest"),
        ("settings", "settings_mismatch"),
        ("content", "content_mismatch"),
        ("content_unavailable", "content_mismatch"),
        ("count", "chunk_count_mismatch"),
        ("valid", "compatible"),
    ],
)
def test_compatibility_reason_matrix(tmp_path, setup, reason) -> None:
    settings, store = arrange_case(tmp_path, setup)

    result = assess_index_compatibility(settings=settings, store=store)

    assert isinstance(result, IndexCompatibility)
    assert result.reason == reason
    assert result.compatible is (reason == "compatible")
    assert (result.fingerprint is not None) is (reason == "compatible")
    assert result.indexed_chunks == (0 if setup in {"unavailable", "empty"} else store.value)
