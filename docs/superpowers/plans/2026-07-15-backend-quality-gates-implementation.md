# Backend Quality Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SE 게시판 코드를 제외한 backend 제품 코드에 85% line coverage gate를 적용하고, 현재 설정·데이터와 정확히 일치하는 manifest가 있는 인덱스에서만 RAG 채팅을 허용하며, backend와 frontend 검사를 GitHub Actions에서 자동 실행한다.

**Architecture:** Chroma 디렉터리의 `index-manifest.json`을 독립 호환성 증거로 사용한다. 인덱싱 CLI가 전체 rebuild 성공 뒤에만 manifest를 원자적으로 기록하고, API는 요청마다 설정·입력 hash·실제 청크 수를 비교해 fail-closed로 동작한다. RAG 객체 cache는 유효 fingerprint를 key로 사용해 데이터 갱신 뒤 오래된 최근 공지와 주제 규칙을 재사용하지 않는다.

**Tech Stack:** Python 3.12/3.13, FastAPI, Pydantic 2, ChromaDB, pytest, pytest-cov, Ruff, Next.js 15, Vitest, TypeScript, ESLint, GitHub Actions

---

## 파일 구조

| 파일 | 책임 |
| --- | --- |
| `backend/app/config.py` | 임베딩 차원·청킹 설정의 단일 입력과 범위 검증 |
| `backend/app/provider_factory.py` | 선택 provider에 설정된 차원을 전달 |
| `backend/app/openai_service.py` | OpenAI embeddings 요청에 차원을 명시 |
| `backend/app/index_manifest.py` | signature, fingerprint, manifest I/O, 호환성 판정 |
| `backend/scripts/index.py` | 전체 rebuild lifecycle과 manifest commit point |
| `backend/app/schemas.py` | health 상태와 index reason API schema |
| `backend/app/main.py` | health/chat fail-closed 및 fingerprint cache 세대 |
| `backend/pyproject.toml` | 제품 코드 coverage 85% gate |
| `.github/workflows/quality.yml` | backend/frontend 독립 CI job |
| `.gitignore` | coverage 산출물 제외 |
| `.env.example`, `README.md`, `docs/rag/operations-evaluation.md` | 운영 설정과 재인덱싱 절차 |
| `docs/PROJECT_STATUS.md`, handoff | 완료 근거와 다음 진입점 |

## Task 1: 설정과 provider 차원 계약

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/provider_factory.py`
- Modify: `backend/app/openai_service.py`
- Modify: `backend/tests/test_config.py`
- Create: `backend/tests/test_provider_factory.py`
- Create: `backend/tests/test_openai_service.py`

- [ ] **Step 1: 설정 기본값과 경계의 failing tests 작성**

`backend/tests/test_config.py`에 환경 변수를 매번 지우고 cache를 복구하는 테스트를 추가한다.

```python
import pytest

from backend.app.config import get_settings


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("EMBEDDING_DIMENSIONS", "255", "EMBEDDING_DIMENSIONS"),
        ("CHUNK_SIZE", "199", "CHUNK_SIZE"),
        ("CHUNK_OVERLAP", "900", "CHUNK_OVERLAP"),
        ("CHUNK_SIZE", "not-an-int", "CHUNK_SIZE"),
    ],
)
def test_index_settings_reject_invalid_values(monkeypatch, name, value, message) -> None:
    monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match=message):
            get_settings()
    finally:
        get_settings.cache_clear()


def test_index_settings_have_stable_defaults(monkeypatch) -> None:
    for name in ("EMBEDDING_DIMENSIONS", "CHUNK_SIZE", "CHUNK_OVERLAP"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.embedding_dimensions == 1536
        assert settings.chunk_size == 900
        assert settings.chunk_overlap == 150
    finally:
        get_settings.cache_clear()
```

- [ ] **Step 2: 설정 tests RED 확인**

Run:

```bash
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_config.py -v
```

Expected: `Settings`에 세 필드가 없고 잘못된 값이 요청한 변수명으로 검증되지 않아 FAIL.

- [ ] **Step 3: Settings와 환경 변수 parser 최소 구현**

`backend/app/config.py`에 다음 parser를 넣는다. 새 필드와 `__post_init__()`는 기존 `cors_origins` 필드 다음에 추가해 직접 생성 코드를 깨지 않도록 기본값을 제공한다.

```python
def _as_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name}는 정수여야 합니다.") from exc


embedding_dimensions: int = 1536
chunk_size: int = 900
chunk_overlap: int = 150

def __post_init__(self) -> None:
    if self.ai_provider not in {"auto", "local", "openai"}:
        raise ValueError("AI_PROVIDER는 auto, local, openai 중 하나여야 합니다.")
    if self.embedding_dimensions < 256:
        raise ValueError("EMBEDDING_DIMENSIONS는 256 이상이어야 합니다.")
    if self.chunk_size < 200:
        raise ValueError("CHUNK_SIZE는 200 이상이어야 합니다.")
    if self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_size:
        raise ValueError("CHUNK_OVERLAP은 0 이상 CHUNK_SIZE 미만이어야 합니다.")
```

`get_settings()` 생성자에는 다음 값을 전달한다.

```python
embedding_dimensions=_as_int("EMBEDDING_DIMENSIONS", 1536),
chunk_size=_as_int("CHUNK_SIZE", 900),
chunk_overlap=_as_int("CHUNK_OVERLAP", 150),
```

- [ ] **Step 4: provider 전달 계약의 failing tests 작성**

`backend/tests/test_provider_factory.py`에서 실제 local 객체와 monkeypatched OpenAI 생성자를 검사한다.

```python
from dataclasses import replace
from unittest.mock import Mock

import pytest

from backend.app import provider_factory
from backend.app.config import get_settings
from backend.app.local_service import LocalHashProvider


def test_local_provider_receives_configured_dimensions() -> None:
    settings = replace(get_settings(), ai_provider="local", embedding_dimensions=384)
    provider = provider_factory.create_provider(settings)
    assert isinstance(provider, LocalHashProvider)
    assert provider.dimensions == 384


def test_openai_provider_receives_models_key_and_dimensions(monkeypatch) -> None:
    constructor = Mock(return_value=object())
    monkeypatch.setattr(provider_factory, "OpenAIProvider", constructor)
    settings = replace(
        get_settings(),
        ai_provider="openai",
        openai_api_key="민감정보 제거됨",
        embedding_dimensions=768,
    )
    provider_factory.create_provider(settings)
    constructor.assert_called_once_with(
        api_key="민감정보 제거됨",
        embedding_model=settings.embedding_model,
        chat_model=settings.chat_model,
        dimensions=768,
    )


def test_explicit_openai_provider_requires_key() -> None:
    settings = replace(get_settings(), ai_provider="openai", openai_api_key=None)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        provider_factory.create_provider(settings)
```

`backend/tests/test_openai_service.py`에는 network가 없는 fake client를 사용한다.

```python
from types import SimpleNamespace
from unittest.mock import Mock

from backend.app.openai_service import OpenAIProvider


def test_openai_embeddings_send_configured_dimensions_and_preserve_order() -> None:
    create = Mock(
        return_value=SimpleNamespace(
            data=[
                SimpleNamespace(index=1, embedding=[0.0, 1.0]),
                SimpleNamespace(index=0, embedding=[1.0, 0.0]),
            ]
        )
    )
    client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
    provider = OpenAIProvider(
        api_key="민감정보 제거됨",
        embedding_model="test-embedding",
        chat_model="test-chat",
        dimensions=2,
        client=client,
    )

    result = provider.embed(["첫 번째", "두 번째"])

    assert result == [[1.0, 0.0], [0.0, 1.0]]
    create.assert_called_once_with(
        model="test-embedding",
        input=["첫 번째", "두 번째"],
        encoding_format="float",
        dimensions=2,
    )
```

- [ ] **Step 5: provider tests RED 확인**

Run:

```bash
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_provider_factory.py backend/tests/test_openai_service.py -v
```

Expected: factory가 dimension을 전달하지 않고 `OpenAIProvider`가 `dimensions`를 받지 않아 FAIL.

- [ ] **Step 6: provider 최소 구현 후 Task 1 GREEN 확인**

`provider_factory.create_provider()`를 다음처럼 변경한다.

```python
if provider_name == "local":
    return LocalHashProvider(dimensions=settings.embedding_dimensions)
# key 검증 유지
return OpenAIProvider(
    api_key=settings.openai_api_key,
    embedding_model=settings.embedding_model,
    chat_model=settings.chat_model,
    dimensions=settings.embedding_dimensions,
)
```

`OpenAIProvider.__init__()`에 keyword-only `dimensions: int`를 추가해 `self.dimensions`에 저장하고 `embeddings.create()`에 `dimensions=self.dimensions`를 전달한다.

Run:

```bash
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_config.py backend/tests/test_provider_factory.py backend/tests/test_openai_service.py backend/tests/test_local_service.py -v
backend/.venv/Scripts/ruff.exe check backend/app/config.py backend/app/provider_factory.py backend/app/openai_service.py backend/tests/test_config.py backend/tests/test_provider_factory.py backend/tests/test_openai_service.py
```

Expected: 모든 대상 test PASS, Ruff `All checks passed!`.

- [ ] **Step 7: Task 1 commit**

```bash
git add backend/app/config.py backend/app/provider_factory.py backend/app/openai_service.py backend/tests/test_config.py backend/tests/test_provider_factory.py backend/tests/test_openai_service.py
git commit -m "feat: make embedding dimensions explicit"
```

## Task 2: 결정적 manifest와 호환성 판정

**Files:**
- Create: `backend/app/index_manifest.py`
- Create: `backend/tests/test_index_manifest.py`

- [ ] **Step 1: manifest 모델·fingerprint·I/O failing tests 작성**

테스트 helper는 임시 raw/rules 파일과 `dataclasses.replace(get_settings(), ...)`를 사용한다.

```python
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


def test_signature_fingerprint_is_deterministic_and_ignores_evidence_fields(tmp_path):
    settings = make_settings(tmp_path)
    signature = build_index_signature(settings)
    first = build_index_manifest(signature, indexed_chunks=3, now=FIXED_TIME)
    second = build_index_manifest(signature, indexed_chunks=9, now=LATER_TIME)
    assert first.fingerprint == second.fingerprint
    assert len(first.fingerprint) == 64


def test_file_hash_changes_for_byte_only_format_change(tmp_path):
    path = tmp_path / "input.json"
    path.write_bytes(b'{"a":1}')
    first = sha256_file(path)
    path.write_bytes(b'{ "a": 1 }')
    assert sha256_file(path) != first


def test_manifest_round_trip_is_atomic_and_strict(tmp_path):
    manifest = make_manifest(tmp_path, indexed_chunks=3)
    path = write_index_manifest(tmp_path / "chroma", manifest)
    assert path.name == "index-manifest.json"
    assert read_index_manifest(tmp_path / "chroma") == manifest
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unexpected"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValidationError):
        read_index_manifest(tmp_path / "chroma")


def test_manifest_rejects_tampered_fingerprint(tmp_path):
    manifest = make_manifest(tmp_path, indexed_chunks=3)
    path = write_index_manifest(tmp_path / "chroma", manifest)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["chunk_size"] = 901
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValidationError, match="fingerprint"):
        read_index_manifest(tmp_path / "chroma")


def test_atomic_writer_removes_temporary_file_when_replace_fails(monkeypatch, tmp_path):
    manifest = make_manifest(tmp_path)
    monkeypatch.setattr(index_manifest.os, "replace", Mock(side_effect=OSError("replace failed")))
    with pytest.raises(OSError, match="replace failed"):
        write_index_manifest(tmp_path / "chroma", manifest)
    assert not (tmp_path / "chroma" / "index-manifest.json").exists()
    assert not list((tmp_path / "chroma").glob("*.tmp"))
```

- [ ] **Step 2: manifest tests RED 확인**

Run:

```bash
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_index_manifest.py -v
```

Expected: `backend.app.index_manifest` import 실패.

- [ ] **Step 3: signature와 manifest 모델 최소 구현**

`backend/app/index_manifest.py`에 다음 public API를 만든다.

```python
INDEX_SCHEMA_VERSION = 1
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


class IndexSignature(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = INDEX_SCHEMA_VERSION
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
```

`sha256_file()`, `fingerprint_for_signature()`, `build_index_signature(settings)`, `build_index_manifest(signature, indexed_chunks, now=None)`를 구현한다. canonical JSON은 `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`를 사용한다. `build_index_signature()`는 `selected_provider_name()`과 `effective_models()`의 embedding 모델을 사용한다.

원자적 writer는 같은 디렉터리의 `NamedTemporaryFile(delete=False)`에 JSON과 마지막 newline을 기록하고 `flush()`, `os.fsync()`, `os.replace()` 순서로 교체한다. `finally`에서 남은 임시 파일을 `unlink(missing_ok=True)`로 제거한다.

- [ ] **Step 4: 모든 호환성 reason의 failing tests 작성**

count를 제어하는 fake와 manifest 변형을 사용해 다음 matrix를 작성한다.

```python
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
        (settings.chroma_path / "index-manifest.json").write_text("{invalid", encoding="utf-8")
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
def test_compatibility_reason_matrix(tmp_path, setup, reason):
    settings, store = arrange_case(tmp_path, setup)
    result = assess_index_compatibility(settings=settings, store=store)
    assert result.reason == reason
    assert result.compatible is (reason == "compatible")
    assert (result.fingerprint is not None) is (reason == "compatible")
```

이 helper는 dimension 변경, raw byte 변경·삭제, manifest 3 대 store 2, 잘못된 JSON을 각각 독립 입력으로 만든다.

- [ ] **Step 5: compatibility RED 확인 후 최소 구현**

Run:

```bash
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_index_manifest.py -v
```

Expected: `assess_index_compatibility`가 없어 reason matrix FAIL.

다음 immutable result와 판정 순서를 구현한다.

```python
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


@dataclass(frozen=True)
class IndexCompatibility:
    compatible: bool
    reason: IndexReason
    indexed_chunks: int
    fingerprint: str | None = None
```

`assess_index_compatibility()`는 count 예외 → 0 count → manifest 없음 → manifest invalid → 설정 필드 → source hash → count 순으로 비교한다. `read_index_manifest()`의 `FileNotFoundError`만 `missing_manifest`, 나머지 읽기·validation 오류는 `invalid_manifest`로 처리한다. 현재 입력 hash 생성의 `OSError`는 `content_mismatch`로 처리한다.

- [ ] **Step 6: Task 2 GREEN과 회귀 확인**

Run:

```bash
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_index_manifest.py backend/tests/test_config.py backend/tests/test_provider_factory.py -v
backend/.venv/Scripts/ruff.exe check backend/app/index_manifest.py backend/tests/test_index_manifest.py
```

Expected: 모든 test PASS, Ruff PASS.

- [ ] **Step 7: Task 2 commit**

```bash
git add backend/app/index_manifest.py backend/tests/test_index_manifest.py
git commit -m "feat: add strict index manifest"
```

## Task 3: 전체 rebuild 인덱싱 CLI

**Files:**
- Modify: `backend/scripts/index.py`
- Create: `backend/tests/test_index_script.py`

- [ ] **Step 1: CLI parsing·reset 보호 failing tests 작성**

`parse_args(argv)`와 아래 fake store/provider를 사용해 호출 순서를 먼저 고정한다.

```python
def make_chunk():
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
    def __init__(self, harness, embedding):
        self.harness = harness
        self.embedding = embedding
        self.embed_calls = 0

    def embed(self, texts):
        self.embed_calls += 1
        self.harness.events.append("embed")
        return self.embedding


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
        embedding,
        upsert_error,
        post_upsert_count,
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
        )
        self.events = []
        self.manifest_removed = False
        self.manifest_written = False
        self.written_manifest = None
        self.changed_inputs = False
        self.signature_calls = 0
        vectors = embedding if embedding is not None else [[0.0] * dimensions]
        self.provider = FakeProvider(self, vectors)
        self.store = FakeStore(self, existing_count, upsert_error, post_upsert_count)


def install_harness(
    monkeypatch,
    tmp_path,
    *,
    existing_count,
    dimensions=256,
    embedding=None,
    upsert_error=None,
    post_upsert_count=None,
    changed_inputs=False,
):
    harness = Harness(
        tmp_path,
        existing_count,
        dimensions,
        embedding,
        upsert_error,
        post_upsert_count,
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
    monkeypatch.setattr(index, "chunk_posts", lambda posts, chunk_size, overlap: [make_chunk()])
    monkeypatch.setattr(index, "ChromaVectorStore", lambda path, name: harness.store)
    monkeypatch.setattr(index, "create_provider", lambda settings: harness.provider)
    monkeypatch.setattr(index, "build_index_signature", signature)
    monkeypatch.setattr(index, "remove_index_manifest", remove_manifest)
    monkeypatch.setattr(index, "write_index_manifest", write_manifest)
    return harness


def test_parse_args_accepts_explicit_argv():
    args = index.parse_args(["--reset", "--chunk-size", "900", "--overlap", "150"])
    assert args.reset is True
    assert args.chunk_size == 900
    assert args.overlap == 150


def test_nonempty_index_requires_reset(monkeypatch, tmp_path, capsys):
    harness = install_harness(monkeypatch, tmp_path, existing_count=3)
    assert index.main([]) == 2
    assert "--reset" in capsys.readouterr().err
    assert harness.provider.embed_calls == 0
    assert harness.store.reset_calls == 0


def test_cli_chunk_override_must_match_settings(monkeypatch, tmp_path, capsys):
    install_harness(monkeypatch, tmp_path, existing_count=0)
    assert index.main(["--chunk-size", "901"]) == 2
    assert "CHUNK_SIZE" in capsys.readouterr().err
```

- [ ] **Step 2: reset tests RED 확인**

Run:

```bash
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_index_script.py -v
```

Expected: `parse_args()`가 argv를 받지 못하고 nonempty index가 계속 upsert되어 FAIL.

- [ ] **Step 3: testable CLI boundary 최소 구현**

`backend/scripts/index.py`를 `parse_args(argv: list[str] | None)`, `run_index(args) -> IndexManifest`, `main(argv: list[str] | None) -> int`로 분리한다. `--chunk-size`, `--overlap` 기본값은 `None`으로 두고 값이 Settings와 다르면 `ValueError`를 발생시킨다. `main()`은 `OSError`, `ValueError`, `RuntimeError`, `openai.OpenAIError`를 stderr의 `인덱싱 오류:`로 바꾸고 exit 2를 반환한다.

- [ ] **Step 4: dimension·commit point failing tests 작성**

다음 테스트는 manifest writer와 reset/upsert 호출 순서를 fake로 기록한다.

```python
def test_embedding_dimension_mismatch_preserves_existing_index(monkeypatch, tmp_path):
    harness = install_harness(
        monkeypatch,
        tmp_path,
        existing_count=3,
        dimensions=256,
        embedding=[[0.0] * 255],
    )
    assert index.main(["--reset"]) == 2
    assert harness.store.reset_calls == 0
    assert harness.manifest_removed is False


def test_failed_upsert_leaves_manifest_invalidated(monkeypatch, tmp_path):
    harness = install_harness(
        monkeypatch,
        tmp_path,
        existing_count=3,
        upsert_error=RuntimeError("fail"),
    )
    assert index.main(["--reset"]) == 2
    assert harness.events == ["embed", "remove_manifest", "reset", "upsert"]
    assert harness.manifest_written is False


def test_success_writes_manifest_after_verified_count(monkeypatch, tmp_path):
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


def test_stored_chunk_count_mismatch_does_not_write_manifest(monkeypatch, tmp_path):
    harness = install_harness(
        monkeypatch,
        tmp_path,
        existing_count=3,
        post_upsert_count=2,
    )
    assert index.main(["--reset"]) == 2
    assert harness.events[-1] == "count_after"
    assert harness.manifest_written is False


def test_input_change_during_embedding_aborts_before_reset(monkeypatch, tmp_path):
    harness = install_harness(
        monkeypatch,
        tmp_path,
        existing_count=3,
        changed_inputs=True,
    )
    assert index.main(["--reset"]) == 2
    assert harness.events == ["embed"]
    assert harness.store.reset_calls == 0
```

test file import에서 `real_build_index_signature`는 `backend.app.index_manifest.build_index_signature`의 원본 alias로 가져와 monkeypatch 뒤에도 실제 signature를 만들게 한다.

- [ ] **Step 5: lifecycle GREEN 구현**

`run_index()` 순서를 다음 코드 구조로 고정한다.

```python
signature_before = build_index_signature(settings)
catalog = load_topic_catalog(settings.topic_rules_path)
posts = enrich_posts(load_posts(settings.raw_posts_path), catalog)
chunks = chunk_posts(posts, chunk_size=settings.chunk_size, overlap=settings.chunk_overlap)
if not chunks:
    raise ValueError("인덱싱할 청크가 없습니다.")

store = ChromaVectorStore(settings.chroma_path, settings.chroma_collection)
if store.count() > 0 and not args.reset:
    raise ValueError("기존 인덱스가 있습니다. python -m backend.scripts.index --reset을 실행하세요.")

provider = create_provider(settings)
embeddings = provider.embed([chunk.text for chunk in chunks])
validate_embedding_dimensions(embeddings, len(chunks), settings.embedding_dimensions)
signature_after = build_index_signature(settings)
if signature_after != signature_before:
    raise ValueError("인덱싱 중 원본 또는 설정이 변경되었습니다. 다시 실행하세요.")

remove_index_manifest(settings.chroma_path)
if args.reset:
    store.reset()
store.upsert(chunks, embeddings)
indexed_chunks = store.count()
if indexed_chunks != len(chunks):
    raise RuntimeError("저장된 청크 수가 생성한 청크 수와 일치하지 않습니다.")
manifest = build_index_manifest(signature_after, indexed_chunks=indexed_chunks)
write_index_manifest(settings.chroma_path, manifest)
return manifest
```

- [ ] **Step 6: Task 3 GREEN과 전체 backend 회귀 확인**

Run:

```bash
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_index_script.py backend/tests/test_index_manifest.py -v
backend/.venv/Scripts/python.exe -m pytest backend/tests
backend/.venv/Scripts/ruff.exe check backend
```

Expected: 신규 tests와 기존 94개 회귀 모두 PASS, Ruff PASS.

- [ ] **Step 7: Task 3 commit**

```bash
git add backend/scripts/index.py backend/tests/test_index_script.py
git commit -m "feat: enforce atomic full index rebuilds"
```

## Task 4: API fail-closed와 fingerprint cache

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_main.py`

- [ ] **Step 1: health 상태 matrix failing tests 작성**

`TestClient(main.app)`와 `IndexCompatibility`를 사용한다. 다음 다섯 상태를 parameterize한다.

```python
def compatibility(reason):
    compatible = reason == "compatible"
    indexed_chunks = 0 if reason in {"empty_index", "index_unavailable"} else 3
    return IndexCompatibility(
        compatible=compatible,
        reason=reason,
        indexed_chunks=indexed_chunks,
        fingerprint="a" * 64 if compatible else None,
    )


@pytest.mark.parametrize(
    ("provider", "key", "reason", "expected"),
    [
        ("openai", None, "compatible", "needs_configuration"),
        ("local", None, "index_unavailable", "unavailable"),
        ("local", None, "empty_index", "needs_index"),
        ("local", None, "content_mismatch", "needs_reindex"),
        ("local", None, "compatible", "ready"),
    ],
)
def test_health_status_matrix(monkeypatch, provider, key, reason, expected):
    settings = replace(main.settings, ai_provider=provider, openai_api_key=key)
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "get_index_compatibility", lambda: compatibility(reason))
    response = TestClient(main.app).get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == expected
    assert response.json()["index_reason"] == reason
    assert response.json()["openai_configured"] is bool(key)
```

- [ ] **Step 2: health RED 확인**

Run:

```bash
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_main.py::test_health_status_matrix -v
```

Expected: 새 status와 index 필드가 schema에 없어 FAIL.

- [ ] **Step 3: HealthResponse와 health 최소 구현**

`HealthResponse.status` literal에 `needs_reindex`, `unavailable`을 추가하고 `index_compatible: bool`, `index_reason: IndexReason`을 추가한다. `main.get_index_compatibility()`는 cache 없이 `assess_index_compatibility(settings=settings, store=get_vector_store())`를 호출한다.

`health()` 상태 우선순위는 다음 순수 분기로 구현한다.

```python
configured = provider_name == "local" or bool(settings.openai_api_key)
if not configured:
    status = "needs_configuration"
elif compatibility.reason == "index_unavailable":
    status = "unavailable"
elif compatibility.reason == "empty_index":
    status = "needs_index"
elif not compatibility.compatible:
    status = "needs_reindex"
else:
    status = "ready"
```

- [ ] **Step 4: chat 차단과 provider 미호출 failing tests 작성**

다음 계약을 각각 TestClient POST로 검증한다.

```python
@pytest.mark.parametrize(
    ("reason", "status", "message"),
    [
        ("index_unavailable", 503, "상태"),
        ("empty_index", 409, "인덱싱"),
        ("missing_manifest", 409, "--reset"),
        ("invalid_manifest", 409, "--reset"),
        ("settings_mismatch", 409, "--reset"),
        ("content_mismatch", 409, "--reset"),
        ("chunk_count_mismatch", 409, "--reset"),
    ],
)
def test_chat_blocks_incompatible_index_before_service(monkeypatch, reason, status, message):
    service = Mock()
    monkeypatch.setattr(main, "get_index_compatibility", lambda: compatibility(reason))
    monkeypatch.setattr(main, "get_rag_service", service)
    response = TestClient(main.app).post("/api/chat", json={"question": "최근 공지 알려줘"})
    assert response.status_code == status
    assert message in response.json()["detail"]
    service.assert_not_called()
```

명시적 OpenAI key 누락은 compatibility 함수와 service가 모두 호출되지 않고 503이어야 한다. compatible case는 fingerprint를 `get_rag_service()`에 전달하고 fake `ChatResponse`를 반환해야 한다.

```python
def test_chat_checks_openai_configuration_before_index(monkeypatch):
    settings = replace(main.settings, ai_provider="openai", openai_api_key=None)
    compatibility_check = Mock()
    service_factory = Mock()
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "get_index_compatibility", compatibility_check)
    monkeypatch.setattr(main, "get_rag_service", service_factory)

    response = TestClient(main.app).post("/api/chat", json={"question": "최근 공지 알려줘"})

    assert response.status_code == 503
    compatibility_check.assert_not_called()
    service_factory.assert_not_called()


def test_chat_passes_compatible_fingerprint_to_service(monkeypatch):
    settings = replace(main.settings, ai_provider="local", openai_api_key=None)
    service = Mock()
    service.ask.return_value = ChatResponse(
        answer="확인했습니다.",
        sources=[],
        grounded=False,
        suggested_questions=[],
        recent_notices=[],
    )
    service_factory = Mock(return_value=service)
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "get_index_compatibility", lambda: compatibility("compatible"))
    monkeypatch.setattr(main, "get_rag_service", service_factory)

    response = TestClient(main.app).post("/api/chat", json={"question": "최근 공지 알려줘"})

    assert response.status_code == 200
    service_factory.assert_called_once_with("a" * 64)
    service.ask.assert_called_once_with("최근 공지 알려줘")
```

- [ ] **Step 5: fingerprint cache failing test 작성**

기존 cache test의 monkeypatch lambda도 fingerprint 인자를 받도록 바꾸고, test 시작·종료 시 세 cache를 모두 `cache_clear()`한다. 같은 fingerprint는 같은 객체, 다른 fingerprint는 새 topic catalog·posts·service를 생성하는지 검증한다.

```python
first = main.get_rag_service("a" * 64)
same = main.get_rag_service("a" * 64)
second = main.get_rag_service("b" * 64)
assert first is same
assert second is not first
assert first.topic_catalog is not second.topic_catalog
```

`get_topic_catalog(fingerprint)`, `get_enriched_posts(fingerprint)`, `get_rag_service(fingerprint)`는 각각 `@lru_cache(maxsize=4)`를 사용한다. fingerprint 인자는 cache 세대 key이며 loader가 파일 path를 선택하는 데 사용하지 않는다.

- [ ] **Step 6: chat·cache GREEN 구현과 endpoint 회귀 확인**

`chat()`은 OpenAI 설정 → compatibility → reason별 HTTPException → compatible service 순서로 구현한다. 오류 detail에는 hash, fingerprint, 절대 경로를 넣지 않는다.

Run:

```bash
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_main.py -v
backend/.venv/Scripts/python.exe -m pytest backend/tests
backend/.venv/Scripts/ruff.exe check backend
```

Expected: endpoint matrix, cache 세대, 기존 backend tests 모두 PASS.

- [ ] **Step 7: Task 4 commit**

```bash
git add backend/app/schemas.py backend/app/main.py backend/tests/test_main.py
git commit -m "feat: block chat on stale indexes"
```

## Task 5: 제품 코드 coverage 85% gate

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `.gitignore`

- [ ] **Step 1: coverage 설정 추가**

`backend/pyproject.toml`에 정확히 다음 설정을 추가한다.

```toml
[tool.coverage.run]
source = ["backend.app", "backend.scripts"]
omit = [
    "*/__init__.py",
    # 사용자 요청에 따라 SE 게시판 수집 구현은 이번 품질 gate에서 제외한다.
    "backend/app/crawling/seboard.py",
]

[tool.coverage.report]
fail_under = 85
show_missing = true
skip_covered = true
```

`.gitignore`에는 다음을 추가한다.

```gitignore
.coverage
coverage.xml
htmlcov/
```

- [ ] **Step 2: 실제 gate 실행**

Run:

```bash
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests --cov=backend.app --cov=backend.scripts --cov-config=backend/pyproject.toml --cov-report=term-missing
```

Expected: SE board와 package initializer가 표에서 제외되고 TOTAL 85% 이상, exit 0. 85% 미만이면 이 계획의 Task 1~4 누락이므로 실행을 중단하고 report의 미실행 계약을 계획에 다시 반영한 뒤 RED→GREEN으로 보강한다. production 동작이나 omit 범위를 coverage 수치만 위해 바꾸지 않는다.

- [ ] **Step 3: 제외 범위 검증**

Run:

```bash
backend/.venv/Scripts/python.exe -m coverage report --show-missing
git check-ignore -v .coverage
```

Expected: `backend.app.crawling.seboard`와 `backend/tests`가 report에 없고 `.coverage`가 `.gitignore`에 의해 제외됨.

- [ ] **Step 4: Task 5 commit**

```bash
git add backend/pyproject.toml .gitignore
git commit -m "test: enforce backend coverage gate"
```

## Task 6: GitHub Actions와 운영 문서

**Files:**
- Create: `.github/workflows/quality.yml`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/rag/operations-evaluation.md`
- Modify: `docs/PROJECT_STATUS.md`

- [ ] **Step 1: 공식 action major version 확인**

GitHub 공식 `actions/checkout`, `actions/setup-python`, `actions/setup-node` release 또는 README를 확인하고 2026-07-15 기준 지원 major를 기록한다. 제3자 블로그나 임의 action을 사용하지 않는다.

- [ ] **Step 2: 최소 권한 CI workflow 작성**

`.github/workflows/quality.yml`을 다음 구조로 만든다. Step 1에서 공식 major가 바뀌었으면 해당 major만 갱신한다.

```yaml
name: Quality

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip
          cache-dependency-path: backend/requirements-dev.txt
      - run: python -m pip install -r backend/requirements-dev.txt
      - run: >-
          python -m pytest -c backend/pyproject.toml backend/tests
          --cov=backend.app --cov=backend.scripts
          --cov-config=backend/pyproject.toml --cov-report=term-missing
        env:
          AI_PROVIDER: local
      - run: python -m ruff check backend

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm --prefix frontend ci
      - run: npm --prefix frontend test
      - run: npm --prefix frontend exec tsc -- --noEmit
      - run: npm --prefix frontend run lint
      - run: npm --prefix frontend run build
```

- [ ] **Step 3: workflow와 동일한 로컬 명령 검증**

Run:

```bash
backend/.venv/Scripts/python.exe -c "import yaml; yaml.safe_load(open('.github/workflows/quality.yml', encoding='utf-8'))"
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests --cov=backend.app --cov=backend.scripts --cov-config=backend/pyproject.toml --cov-report=term-missing
backend/.venv/Scripts/python.exe -m ruff check backend
npm --prefix frontend test
npm --prefix frontend exec tsc -- --noEmit
npm --prefix frontend run lint
npm --prefix frontend run build
```

Expected: YAML parse exit 0, backend coverage 85% 이상, Ruff PASS, frontend 9개 이상 tests·typecheck·lint·build PASS.

- [ ] **Step 4: 설정과 운영 문서 갱신**

`.env.example`의 RAG 구간에 다음 값을 추가한다.

```dotenv
EMBEDDING_DIMENSIONS=1536
CHUNK_SIZE=900
CHUNK_OVERLAP=150
```

`README.md`와 `docs/rag/operations-evaluation.md`에는 다음을 명시한다.

- 설정·raw posts·topic rules 변경 후 `python -m backend.scripts.index --reset`
- manifest는 `CHROMA_PATH/index-manifest.json`이며 Chroma와 함께 생성·백업
- `needs_configuration`, `unavailable`, `needs_index`, `needs_reindex`, `ready` 대응
- chat 409은 인덱싱/reset 필요, 503은 provider 설정 또는 저장소 상태 확인
- 제품 코드 coverage 표준 명령

`docs/PROJECT_STATUS.md`에서 P1-1, P1-2, P1-4를 로컬 완료로 옮기고 측정 test 수·coverage·manifest fingerprint 앞 12자리·CI 파일을 기록한다. GitHub 원격 실행 전에는 “workflow 작성·로컬 명령 통과”와 “GitHub Actions 원격 통과”를 구분한다.

- [ ] **Step 5: Task 6 commit**

```bash
git add .github/workflows/quality.yml .env.example README.md docs/rag/operations-evaluation.md docs/PROJECT_STATUS.md
git commit -m "ci: add backend and frontend quality gates"
```

## Task 7: 실제 재인덱싱·품질 회귀·인수인계

**Files:**
- Create: `docs/superpowers/handoffs/2026-07-15-backend-quality-gates-handoff.md`
- Modify: `docs/PROJECT_STATUS.md` if measured values differ from Task 6 assumptions

- [ ] **Step 1: 실제 local 전체 재인덱싱**

Run:

```bash
backend/.venv/Scripts/python.exe -m backend.scripts.index --reset
backend/.venv/Scripts/python.exe -c "from backend.app.config import get_settings; from backend.app.index_manifest import read_index_manifest; m=read_index_manifest(get_settings().chroma_path); print(m.indexed_chunks, m.fingerprint[:12])"
```

Expected: 50 posts에서 1개 이상의 chunk를 저장하고 manifest count와 실제 count가 일치하며 fingerprint 앞 12자리를 출력.

- [ ] **Step 2: RAG 평가와 데이터 감사 실행**

Run:

```bash
backend/.venv/Scripts/python.exe -m backend.scripts.evaluate
backend/.venv/Scripts/python.exe -m backend.scripts.audit_data
```

Expected: 평가 30/30, exit 0. 감사 50 posts와 `missing_source`, `stale_topic`, `empty_topic` 3경고, 의도된 exit 1. SE 경고를 숨기거나 데이터를 수정하지 않는다.

- [ ] **Step 3: API 상태와 차단 smoke test**

실제 worktree 인덱스의 health와 임시 입력 변경 회귀를 다음 명령으로 확인한다.

```bash
backend/.venv/Scripts/python.exe -c "from backend.app.main import health; result=health(); assert result.status == 'ready', result; print(result.status, result.index_reason, result.indexed_chunks)"
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_index_manifest.py::test_compatibility_reason_matrix backend/tests/test_main.py::test_chat_blocks_incompatible_index_before_service -v
```

Expected: 실제 health가 `ready compatible`과 실제 청크 수를 출력하고, temp path를 사용하는 reason matrix와 chat 차단 parameter cases가 모두 PASS. tracked raw posts는 변경되지 않음.

- [ ] **Step 4: 전체 최종 검증**

Run:

```bash
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests --cov=backend.app --cov=backend.scripts --cov-config=backend/pyproject.toml --cov-report=term-missing
backend/.venv/Scripts/python.exe -m ruff check backend
npm --prefix frontend test
npm --prefix frontend exec tsc -- --noEmit
npm --prefix frontend run lint
npm --prefix frontend run build
git diff --check
git status --short
```

Expected: coverage 85% 이상, 모든 test·정적 검사·build PASS, diff whitespace 오류 없음. Git status에는 의도한 handoff/status 변경만 보이고 `.coverage`, Chroma, 평가·감사 보고서는 보이지 않음.

- [ ] **Step 5: 민감정보·범위 검사**

Run:

```bash
git diff --name-only 3c016de...HEAD
git diff 3c016de...HEAD -- backend/app/crawling/seboard.py
rg -n "OPENAI_API_KEY=.+|PASSWORD=.+|Bearer [A-Za-z0-9]" .github backend docs README.md .env.example
```

Expected: SE board diff 없음. secret 값 검색 결과 없음. 문서 예시의 빈 key와 `민감정보 제거됨`만 허용.

- [ ] **Step 6: handoff 작성**

handoff에 다음 실제 값을 기록한다.

- 브랜치와 Task별 commit hash
- backend test 수와 line coverage
- frontend test 수, type/lint/build 결과
- 실제 posts/chunks/fingerprint 앞 12자리
- 평가 30/30과 감사 3경고 exit 1
- GitHub workflow는 로컬 검증 완료인지 원격 run도 완료인지 구분
- SE 게시판 무변경 확인
- 후속 묶음: frontend E2E/접근성, 관측성/rate limit, Docker health/backup

- [ ] **Step 7: handoff commit**

```bash
git add docs/superpowers/handoffs/2026-07-15-backend-quality-gates-handoff.md docs/PROJECT_STATUS.md
git commit -m "docs: hand off backend quality gates"
```

- [ ] **Step 8: 완료 전 리뷰와 브랜치 마무리**

`superpowers:requesting-code-review`, `superpowers:verification-before-completion`, `superpowers:finishing-a-development-branch`를 순서대로 적용한다. 리뷰에서 발견된 결함은 재현 test를 먼저 추가한 뒤 수정한다. 최종 상태에서 사용자에게 병합·PR·브랜치 유지 선택지를 제시한다.
