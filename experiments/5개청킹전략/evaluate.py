"""
evaluate.py
─────────────────────────────────────────
5개 컬렉션의 검색 성능을 비교 측정한다.

■ 왜 "문서 단위"로 평가하는가
  전략마다 청크 수가 다르다 (850 ~ 1,980개).
  청크 단위로 평가하면 청크를 잘게 쪼갠 전략이 불리해진다.
  같은 문서에서 나온 청크 3개가 검색되면, 사실상 문서 1개를 찾은 건데
  청크 기준으로는 "3개 중 3개 정답"처럼 부풀려 보이거나
  반대로 상위 K개를 한 문서가 독식해 다른 정답을 밀어낼 수도 있다.

  그래서 "정답 문서가 상위 K개 청크 안에 등장했는가"로 측정한다.
  이러면 전략 간 비교가 공정해진다.

■ 지표
  Recall@K : 정답 문서가 상위 K개 청크 안에 포함된 질문의 비율
  MRR      : 정답 문서가 처음 등장한 순위의 역수 평균 (1등=1.0, 2등=0.5, ...)

사용법:
  python evaluate.py
  python evaluate.py --k 3 5 10
"""

import os
import sys
import json
import argparse
from collections import defaultdict

import chromadb
from chromadb.utils import embedding_functions

from chunking_strategies import STRATEGIES

DB_PATH = "./chroma_db"
EVALSET_PATH = "evalset.json"


def get_embedding_function():
    """build_dbs.py와 반드시 동일한 임베딩 함수를 써야 한다."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("\n⚠️  OPENAI_API_KEY 환경변수가 필요합니다.\n")
        sys.exit(1)
    return embedding_functions.OpenAIEmbeddingFunction(
        api_key=api_key,
        model_name="text-embedding-3-small",
    )


def evaluate_collection(collection, evalset: list, k_list: list[int]) -> dict:
    """
    컬렉션 하나를 평가한다.
    반환: {"recall@k": {...}, "mrr": float, "details": [...]}
    """
    max_k = max(k_list)
    hits = {k: 0 for k in k_list}
    reciprocal_ranks = []
    details = []

    for q in evalset:
        results = collection.query(query_texts=[q["question"]], n_results=max_k)
        metadatas = results["metadatas"][0]

        # 검색된 청크들이 어느 원본 문서에서 왔는지 순서대로 나열
        retrieved_docs = [m.get("doc_id") for m in metadatas]
        answers = set(q["answer_doc_ids"])

        # 정답 문서가 처음 등장한 순위 찾기 (1-base)
        first_hit_rank = None
        for rank, doc_id in enumerate(retrieved_docs, start=1):
            if doc_id in answers:
                first_hit_rank = rank
                break

        for k in k_list:
            if first_hit_rank is not None and first_hit_rank <= k:
                hits[k] += 1

        reciprocal_ranks.append(1.0 / first_hit_rank if first_hit_rank else 0.0)

        details.append({
            "question": q["question"],
            "type": q.get("type", ""),
            "first_hit_rank": first_hit_rank,
            "retrieved_top3": retrieved_docs[:3],
        })

    n = len(evalset)
    return {
        "recall": {k: hits[k] / n for k in k_list},
        "mrr": sum(reciprocal_ranks) / n,
        "details": details,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", nargs="+", type=int, default=[1, 3, 5, 10],
                        help="측정할 K 값들 (기본: 1 3 5 10)")
    args = parser.parse_args()
    k_list = sorted(args.k)

    with open(EVALSET_PATH, encoding="utf-8") as f:
        evalset = json.load(f)
    print(f"평가 질문: {len(evalset)}개\n")

    embed_fn = get_embedding_function()
    client = chromadb.PersistentClient(path=DB_PATH)

    results = {}
    for key, (desc, _) in STRATEGIES.items():
        try:
            collection = client.get_collection(name=key, embedding_function=embed_fn)
        except Exception:
            print(f"⚠️  '{key}' 컬렉션이 없습니다. build_dbs.py를 먼저 실행하세요.")
            continue
        print(f"평가 중: {key} ...", end=" ", flush=True)
        results[key] = evaluate_collection(collection, evalset, k_list)
        results[key]["desc"] = desc
        results[key]["count"] = collection.count()
        print("완료")

    if not results:
        return

    # ── 결과 표 ──
    print("\n" + "=" * 78)
    print("  청킹 전략별 검색 성능 비교")
    print("=" * 78)
    header = f"  {'전략':<18} {'청크수':>7}"
    for k in k_list:
        header += f" {'R@'+str(k):>7}"
    header += f" {'MRR':>7}"
    print(header)
    print("  " + "─" * 74)

    for key, r in results.items():
        line = f"  {key:<18} {r['count']:>7}"
        for k in k_list:
            line += f" {r['recall'][k]*100:>6.1f}%"
        line += f" {r['mrr']:>7.3f}"
        print(line)

    # ── 최고 성능 전략 ──
    best_k = k_list[len(k_list) // 2]
    best = max(results.items(), key=lambda x: (x[1]["recall"][best_k], x[1]["mrr"]))
    print("\n  " + "─" * 74)
    print(f"  최고 성능 (R@{best_k} 기준): {best[0]} — {best[1]['desc']}")

    # ── 질문 유형별 분석 ──
    print("\n" + "=" * 78)
    print("  질문 유형별 정답률 (R@5)")
    print("=" * 78)
    types = sorted({q.get("type", "") for q in evalset})
    print(f"  {'유형':<14}", end="")
    for key in results:
        print(f"{key[:12]:>14}", end="")
    print()
    print("  " + "─" * 74)
    for t in types:
        print(f"  {t:<14}", end="")
        for key, r in results.items():
            sub = [d for d in r["details"] if d["type"] == t]
            if not sub:
                print(f"{'-':>14}", end="")
                continue
            hit = sum(1 for d in sub
                      if d["first_hit_rank"] and d["first_hit_rank"] <= 5)
            print(f"{hit}/{len(sub):<12}", end="")
        print()

    # ── 실패 질문 ──
    print("\n" + "=" * 78)
    print("  어느 전략에서도 못 찾은 질문 (R@10 기준)")
    print("=" * 78)
    fail_count = defaultdict(int)
    for key, r in results.items():
        for d in r["details"]:
            if d["first_hit_rank"] is None:
                fail_count[d["question"]] += 1
    all_fail = [q for q, c in fail_count.items() if c == len(results)]
    if all_fail:
        for q in all_fail:
            print(f"  · {q}")
        print("\n  → 이런 질문은 청킹 문제가 아니라 데이터 자체에 답이 없거나,")
        print("     검색 방식(임베딩·Hybrid Search) 개선이 필요한 경우입니다.")
    else:
        print("  없음 — 모든 질문이 최소 한 전략에서는 검색됨")

    with open("eval_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n  상세 결과 저장: eval_results.json")
    print("=" * 78)


if __name__ == "__main__":
    main()
