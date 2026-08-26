"""
chunking_strategies.py
─────────────────────────────────────────
비교 실험용 5가지 청킹 전략 정의.

각 전략은 documents_clean.json(850건)을 입력받아
청크 리스트를 반환한다. 반환 형식은 모두 동일하다.

전략 설계 의도:
  S1: 베이스라인 — 자르지 않음. 데이터가 짧으면 이게 최선일 수 있다.
  S2: 작게 자르기 — 검색 정밀도↑, 문맥↓
  S3: 크게 자르기 — 문맥↑, 정밀도↓
  S4: 구분자 인식 분할 — 문장 경계 존중
  S5: S4 + 한국어 구분자 + 헤더 재주입 — 우리가 제안하는 방식

S2·S3을 함께 두는 이유: 청크 "크기"만의 효과를 분리해서 보기 위함.
S4·S5를 함께 두는 이유: "한국어 구분자 + 헤더 재주입"의 효과만 보기 위함.
"""

import re
from langchain_text_splitters import (
    CharacterTextSplitter,
    RecursiveCharacterTextSplitter,
)

HEADER_KEY_PATTERN = re.compile(r"^(제목|출처|분류|작성일|원문URL|작성자):")


def split_header_body(page_content: str) -> tuple[str, str]:
    """문서를 헤더 블록과 본문으로 분리."""
    lines = page_content.split("\n")
    header_lines, idx = [], 0
    for i, line in enumerate(lines):
        if HEADER_KEY_PATTERN.match(line):
            header_lines.append(line)
            idx = i + 1
        elif not line.strip() and header_lines:
            idx = i + 1
        else:
            break
    return "\n".join(header_lines), "\n".join(lines[idx:])


def _make_chunk(text: str, doc: dict, seq: int) -> dict:
    """청크 하나 생성. 원본 metadata를 보존하고 추적 정보만 추가한다."""
    meta = dict(doc["metadata"])
    meta["doc_id"] = doc["metadata"]["id"]      # 원본 문서 추적 (평가에 필수)
    meta["chunk_seq"] = seq
    meta["id"] = f"{doc['metadata']['id']}__{seq}"
    return {"page_content": text, "metadata": meta}


# ═══════════════════════════════════════════
# S1. 분할 없음 (베이스라인)
# ═══════════════════════════════════════════
def strategy_nosplit(docs: list[dict]) -> list[dict]:
    """1문서 = 1청크. 자르지 않는다."""
    return [_make_chunk(d["page_content"], d, 0) for d in docs]


# ═══════════════════════════════════════════
# S2. 고정 500자
# ═══════════════════════════════════════════
def strategy_fixed_500(docs: list[dict]) -> list[dict]:
    """문자 수 기준 고정 분할(작게). 구분자를 거의 고려하지 않는다."""
    splitter = CharacterTextSplitter(
        separator="",              # 구분자 무시 → 순수 길이 기준
        chunk_size=500,
        chunk_overlap=100,
        length_function=len,
    )
    out = []
    for d in docs:
        for i, part in enumerate(splitter.split_text(d["page_content"])):
            out.append(_make_chunk(part, d, i))
    return out


# ═══════════════════════════════════════════
# S3. 고정 1000자
# ═══════════════════════════════════════════
def strategy_fixed_1000(docs: list[dict]) -> list[dict]:
    """문자 수 기준 고정 분할(크게). S2와 비교해 '크기 효과'만 본다."""
    splitter = CharacterTextSplitter(
        separator="",
        chunk_size=1000,
        chunk_overlap=150,
        length_function=len,
    )
    out = []
    for d in docs:
        for i, part in enumerate(splitter.split_text(d["page_content"])):
            out.append(_make_chunk(part, d, i))
    return out


# ═══════════════════════════════════════════
# S4. Recursive (기본 구분자)
# ═══════════════════════════════════════════
def strategy_recursive_default(docs: list[dict]) -> list[dict]:
    """LangChain 기본 구분자로 재귀 분할. 문장 경계를 존중한다."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
        separators=["\n\n", "\n", " ", ""],     # 라이브러리 기본값
        length_function=len,
    )
    out = []
    for d in docs:
        for i, part in enumerate(splitter.split_text(d["page_content"])):
            out.append(_make_chunk(part, d, i))
    return out


# ═══════════════════════════════════════════
# S5. Recursive + 한국어 구분자 + 헤더 재주입
# ═══════════════════════════════════════════
def strategy_recursive_korean(docs: list[dict]) -> list[dict]:
    """
    S4에 두 가지를 추가한 버전.
      (1) 한국어 종결어미를 구분자에 추가 → 문장 경계가 더 정확해짐
      (2) 분할된 모든 조각에 헤더 재주입 → 2번째 이후 청크도 맥락 유지

    S4와의 성능 차이 = 이 두 기법의 순수 효과.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
        separators=["\n\n", "\n", "다. ", "요. ", "음. ", ". ", ", ", " ", ""],
        length_function=len,
    )
    out = []
    for d in docs:
        header, body = split_header_body(d["page_content"])

        # 본문이 짧으면 자르지 않음 (헤더 중복만 늘어나므로)
        if len(body) <= 800:
            out.append(_make_chunk(d["page_content"], d, 0))
            continue

        for i, part in enumerate(splitter.split_text(body)):
            text = f"{header}\n\n{part}" if header else part
            out.append(_make_chunk(text, d, i))
    return out


# ═══════════════════════════════════════════
# 전략 레지스트리
# ═══════════════════════════════════════════
STRATEGIES = {
    "S1_nosplit":         ("분할 없음 (베이스라인)",              strategy_nosplit),
    "S2_fixed500":        ("고정 500자 / overlap 100",            strategy_fixed_500),
    "S3_fixed1000":       ("고정 1000자 / overlap 150",           strategy_fixed_1000),
    "S4_recursive":       ("Recursive 800 / 기본 구분자",          strategy_recursive_default),
    "S5_recursive_ko":    ("Recursive 800 / 한국어 구분자+헤더",   strategy_recursive_korean),
}
