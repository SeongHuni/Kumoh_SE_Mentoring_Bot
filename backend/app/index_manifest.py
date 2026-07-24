from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.config import Settings
from backend.app.provider_factory import effective_models, selected_provider_name

INDEX_SCHEMA_VERSION = 5
MANIFEST_FILENAME = "index-manifest.json"
SIGNATURE_FIELDS = (
    "schema_version",
    "collection",
    "provider",
    "embedding_model",
    "embedding_dimensions",
    "chunk_size",
    "chunk_overlap",
    "raw_posts_sha256",
    "topic_rules_sha256",
)
SETTINGS_FIELDS = (
    "schema_version",
    "collection",
    "provider",
    "embedding_model",
    "embedding_dimensions",
    "chunk_size",
    "chunk_overlap",
)
CONTENT_FIELDS = ("raw_posts_sha256", "topic_rules_sha256")

IndexReason = Literal[
    "compatible",
    "empty_index",
    "index_unavailable",
    "missing_manifest",
    "invalid_manifest",
    "settings_mismatch",
    "content_mismatch",
    "chunk_count_mismatch",
]


class IndexSignature(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[5] = INDEX_SCHEMA_VERSION
    collection: str = Field(min_length=1)
    provider: Literal["local", "openai"]
    embedding_model: str = Field(min_length=1)
    embedding_dimensions: int = Field(ge=256)
    chunk_size: int = Field(ge=200)
    chunk_overlap: int = Field(ge=0)
    raw_posts_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    topic_rules_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_overlap(self) -> Self:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap은 chunk_size 미만이어야 합니다.")
        return self


class IndexManifest(IndexSignature):
    indexed_chunks: int = Field(gt=0)
    generated_at: datetime
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_integrity(self) -> Self:
        if self.generated_at.utcoffset() != timedelta(0):
            raise ValueError("generated_at은 UTC여야 합니다.")
        if self.fingerprint != fingerprint_for_signature(self):
            raise ValueError("manifest fingerprint가 일치하지 않습니다.")
        return self


@dataclass(frozen=True)
class IndexCompatibility:
    compatible: bool
    reason: IndexReason
    indexed_chunks: int
    fingerprint: str | None = None
    generation: str | None = None


class CountableStore(Protocol):
    def count(self) -> int: ...


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fingerprint_for_signature(signature: IndexSignature) -> str:
    payload = {name: getattr(signature, name) for name in SIGNATURE_FIELDS}
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def build_index_signature(settings: Settings) -> IndexSignature:
    _, embedding_model = effective_models(settings)
    return IndexSignature(
        collection=settings.chroma_collection,
        provider=selected_provider_name(settings),
        embedding_model=embedding_model,
        embedding_dimensions=settings.embedding_dimensions,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        raw_posts_sha256=sha256_file(settings.raw_posts_path),
        topic_rules_sha256=sha256_file(settings.topic_rules_path),
    )


def build_index_manifest(
    signature: IndexSignature,
    *,
    indexed_chunks: int,
    now: datetime | None = None,
) -> IndexManifest:
    return IndexManifest(
        **signature.model_dump(),
        indexed_chunks=indexed_chunks,
        generated_at=now or datetime.now(UTC),
        fingerprint=fingerprint_for_signature(signature),
    )


def index_manifest_path(chroma_path: Path) -> Path:
    return chroma_path / MANIFEST_FILENAME


def write_index_manifest(chroma_path: Path, manifest: IndexManifest) -> Path:
    chroma_path.mkdir(parents=True, exist_ok=True)
    destination = index_manifest_path(chroma_path)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{MANIFEST_FILENAME}.",
            suffix=".tmp",
            dir=chroma_path,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(manifest.model_dump_json(indent=2))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, destination)
        temporary_path = None
        return destination
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def read_index_manifest(chroma_path: Path) -> IndexManifest:
    payload = index_manifest_path(chroma_path).read_text(encoding="utf-8")
    return IndexManifest.model_validate_json(payload)


def remove_index_manifest(chroma_path: Path) -> None:
    index_manifest_path(chroma_path).unlink(missing_ok=True)


def _fields_match(
    actual: IndexManifest,
    expected: IndexSignature,
    field_names: tuple[str, ...],
) -> bool:
    return all(getattr(actual, name) == getattr(expected, name) for name in field_names)


def assess_index_compatibility(
    *,
    settings: Settings,
    store: CountableStore,
) -> IndexCompatibility:
    try:
        indexed_chunks = int(store.count())
    except Exception:
        return IndexCompatibility(False, "index_unavailable", 0)

    if indexed_chunks < 1:
        return IndexCompatibility(False, "empty_index", 0)

    try:
        manifest = read_index_manifest(settings.chroma_path)
    except FileNotFoundError:
        return IndexCompatibility(False, "missing_manifest", indexed_chunks)
    except (OSError, ValueError):
        return IndexCompatibility(False, "invalid_manifest", indexed_chunks)

    try:
        expected = build_index_signature(settings)
    except OSError:
        return IndexCompatibility(False, "content_mismatch", indexed_chunks)

    if not _fields_match(manifest, expected, SETTINGS_FIELDS):
        return IndexCompatibility(False, "settings_mismatch", indexed_chunks)
    if not _fields_match(manifest, expected, CONTENT_FIELDS):
        return IndexCompatibility(False, "content_mismatch", indexed_chunks)
    if manifest.indexed_chunks != indexed_chunks:
        return IndexCompatibility(False, "chunk_count_mismatch", indexed_chunks)
    return IndexCompatibility(
        True,
        "compatible",
        indexed_chunks,
        fingerprint=manifest.fingerprint,
        generation=manifest.generated_at.isoformat(),
    )
