"""되묻기가 답변 품질을 올리는지 측정한다.

되묻기는 설계상 이점(검색·생성 모델을 호출하지 않아 비용과 지연이 0)은
분명하지만, 답변 품질을 올리는지는 재본 적이 없었다. 그래서 잰다.

되묻기가 걸리는 질문마다 세 경로를 돌려 비교한다.

  A  되묻기      선택지 첫 번째를 고른 뒤 답변까지. 사용자는 2턴을 쓴다.
  B  계획기 검색  되묻기만 금지하고 계획기가 질의를 다시 쓰게 한다. 1턴.
  C  원문 검색    질문을 그대로 검색한다. 계획기가 없을 때의 바닥값. 1턴.

세 경로의 답변을 같은 기준으로 채점한다. B 가 A 만큼 좋다면 되묻기는
사용자에게 한 턴을 더 요구하고 얻는 것이 없다는 뜻이다.

  python scripts/measure_clarify.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from backend.app.config import get_settings
from backend.app.provider_factory import create_provider
from backend.app.query_planner import (
    RESPONSE_SCHEMA,
    SearchPlan,
    build_system,
    plan_search,
)
from backend.app.ranking import (
    apply_scoring,
    diversify,
    load_scoring_config,
    prefer_recent_among_similar,
)
from backend.app.session import Session
from backend.app.vector_store import ChromaVectorStore

# 애매해 보이는 질문들. 되묻기가 걸리는지부터 확인한 뒤 걸린 것만 비교한다.
CANDIDATES = [
    "장학금",
    "신청 어떻게 해?",
    "일정 알려줘",
    "언제야?",
    "모집 공고 있어?",
    "상담 받고 싶어",
    "등록금 얼마야?",
    "지원 받을 수 있어?",
    "기간이 언제까지야?",
    "어디서 확인해?",
    "캡스톤",
    "수업 추천해줘",
    "공지 알려줘",
    "신청 기간",
    "제출해야 하는 서류가 뭐야?",
]

TOP_K = 5
FETCH_K = 100


def force_search_plan(provider, question: str) -> SearchPlan:
    """되묻기를 금지한 채 계획기를 돌린다.

    프로덕션 코드를 건드리지 않으려고 시스템 프롬프트만 덧붙여 호출한다.
    """
    system = build_system_no_clarify()
    raw = provider.chat_json(
        system=system,
        user=f'<conversation_history untrusted="true" count="0" />\n[현재 질문]\n{question}',
        schema=RESPONSE_SCHEMA,
        schema_name="search_plan",
    )
    query = str(raw.get("standalone_query") or "").strip() or question
    mode = (raw.get("temporal_constraint") or {}).get("mode")
    plan = SearchPlan(action="search", standalone_query=query)
    if mode in ("none", "explicit", "latest"):
        plan.temporal_constraint.mode = mode
    return plan


def build_system_no_clarify() -> str:
    from datetime import date

    base = build_system(date.today().isoformat())
    return base + (
        "\n\n[이번 호출의 예외]\n"
        "action 은 반드시 search 로 한다. clarify 와 reject 를 쓰지 않는다.\n"
        "대상이 애매하더라도 가장 그럴듯한 해석 하나를 골라 standalone_query 를 만든다."
    )


def retrieve(store, provider, scoring, plan: SearchPlan):
    embedding = provider.embed([plan.standalone_query])[0]
    items = store.query(embedding, FETCH_K)
    if not items:
        return []
    items = apply_scoring(items, scoring)
    if plan.temporal_constraint.mode == "latest":
        items = prefer_recent_among_similar(items, TOP_K * 2)
    return diversify(items, TOP_K, max_per_doc=2, max_per_topic=2)


def grade(answer: str) -> dict:
    text = (answer or "").strip()
    first = text.split("\n")[0]
    citations = len(re.findall(r"\[(?:자료\s*)?\d{1,2}\]", text))
    refused = bool(re.search(r"확인할 수 없|찾지 못했|찾을 수 없", first)) and len(text) < 200
    return {
        "citations": citations,
        "length": len(text),
        "refused": refused,
        # 좋은 답: 거부가 아니고, 인용이 붙고, 설명이 될 만큼 길다
        "ok": (not refused) and citations > 0 and len(text) >= 100,
        "preview": text.replace("\n", " ")[:64],
    }


def main() -> None:
    settings = get_settings()
    provider = create_provider(settings)
    store = ChromaVectorStore(
        settings.chroma_path, settings.chroma_collection, settings.chroma_url
    )
    scoring = load_scoring_config(settings.importance_path)

    print("=== 1) 되묻기가 걸리는 질문 찾기 ===")
    ambiguous = []
    for question in CANDIDATES:
        plan = plan_search(provider, Session(), question)
        mark = "되묻기" if plan.action == "clarify" else plan.action
        print(f"  {mark:8s} {question}")
        if plan.action == "clarify" and plan.clarification_candidates:
            ambiguous.append((question, plan))

    if not ambiguous:
        print("\n되묻기가 걸리는 질문이 없다. 비교할 것이 없음.")
        return

    print(f"\n=== 2) 되묻기 {len(ambiguous)}건 · 세 경로 비교 ===\n")
    rows = []
    for question, plan in ambiguous:
        first_option = plan.clarification_candidates[0]

        # A: 되묻기 -> 첫 선택지를 고른 뒤 검색 (사용자는 2턴을 썼다)
        plan_a = SearchPlan(action="search", standalone_query=first_option.query)
        got_a = retrieve(store, provider, scoring, plan_a)
        ans_a = provider.answer(question, got_a) if got_a else ""

        # B: 되묻기 금지, 계획기가 질의를 다시 씀 (1턴)
        plan_b = force_search_plan(provider, question)
        got_b = retrieve(store, provider, scoring, plan_b)
        ans_b = provider.answer(question, got_b) if got_b else ""

        # C: 원문 그대로 검색 (1턴)
        plan_c = SearchPlan(action="search", standalone_query=question)
        got_c = retrieve(store, provider, scoring, plan_c)
        ans_c = provider.answer(question, got_c) if got_c else ""

        ga, gb, gc = grade(ans_a), grade(ans_b), grade(ans_c)
        rows.append(
            {
                "question": question,
                "clarify_options": [c.label for c in plan.clarification_candidates],
                "A_query": plan_a.standalone_query,
                "B_query": plan_b.standalone_query,
                "A": ga,
                "B": gb,
                "C": gc,
            }
        )

        print(f'"{question}"')
        print(f"   선택지: {', '.join(c.label for c in plan.clarification_candidates)}")
        print(f"   A 되묻기(2턴)  {'양호' if ga['ok'] else '미흡'}  {ga['citations']}인용 {ga['length']:4d}자  <- {plan_a.standalone_query}")
        print(f"   B 계획기검색   {'양호' if gb['ok'] else '미흡'}  {gb['citations']}인용 {gb['length']:4d}자  <- {plan_b.standalone_query}")
        print(f"   C 원문검색     {'양호' if gc['ok'] else '미흡'}  {gc['citations']}인용 {gc['length']:4d}자")
        print()

    total = len(rows)
    a_ok = sum(1 for r in rows if r["A"]["ok"])
    b_ok = sum(1 for r in rows if r["B"]["ok"])
    c_ok = sum(1 for r in rows if r["C"]["ok"])

    print("=== 3) 요약 ===")
    print(f"  대상 {total}건")
    print(f"  A 되묻기(2턴)   양호 {a_ok}/{total}")
    print(f"  B 계획기검색(1턴) 양호 {b_ok}/{total}")
    print(f"  C 원문검색(1턴)   양호 {c_ok}/{total}")
    print()
    if b_ok >= a_ok:
        print("  B 가 A 이상이다. 되묻기는 한 턴을 더 요구하고 얻는 것이 없다.")
    else:
        print(f"  A 가 B 보다 {a_ok - b_ok}건 낫다. 되묻기가 실제로 도움이 된다.")

    out = ROOT / "outputs" / "eval_results" / "clarify_vs_search.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
