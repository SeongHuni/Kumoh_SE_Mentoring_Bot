"""
build_dbs.py
─────────────────────────────────────────
5가지 청킹 전략별로 Chroma 컬렉션을 각각 구축한다.

사용법:
  # 1. 환경변수에 API 키 설정
  set OPENAI_API_KEY=sk-...        (Windows)
  export OPENAI_API_KEY=sk-...     (Mac/Linux)

  # 2. 실행
  python build_dbs.py

  # 특정 전략만 다시 만들고 싶을 때
  python build_dbs.py --only S5_recursive_ko

주의:
  - 임베딩 API 호출 비용이 발생한다. 전체 약 7,200청크 기준
    text-embedding-3-small로 대략 100원 내외 (2026년 기준 추정).
  - 한 번 만들어두면 chroma_db/ 폴더에 저장되어 재사용된다.
"""

import os
import sys
import json
import time
import argparse

import chromadb
from chromadb.utils import embedding_functions

from chunking_strategies import STRATEGIES

INPUT_PATH = "documents_clean.json"
DB_PATH = "./chroma_db"
BATCH_SIZE = 100          # 임베딩 API 호출 단위


def get_embedding_function():
    """
    임베딩 함수를 반환한다.

    기본은 OpenAI. 비용을 아끼거나 오프라인에서 실험하려면
    아래 주석의 로컬 모델로 교체할 수 있다.
    단, 5개 DB 모두 반드시 '같은' 임베딩 모델을 써야 비교가 공정하다.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("\n⚠️  OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
        print("    set OPENAI_API_KEY=sk-...  (Windows)")
        print("    export OPENAI_API_KEY=sk-...  (Mac/Linux)\n")
        sys.exit(1)

    return embedding_functions.OpenAIEmbeddingFunction(
        api_key=api_key,
        model_name="text-embedding-3-small",
    )

    # ── 로컬 모델을 쓰고 싶다면 위를 주석 처리하고 아래 사용 ──
    # return embedding_functions.SentenceTransformerEmbeddingFunction(
    #     model_name="jhgan/ko-sroberta-multitask"
    # )


def build_collection(client, name: str, chunks: list[dict], embed_fn):
    """전략 하나에 대한 컬렉션을 구축한다."""
    # 기존 컬렉션이 있으면 삭제 후 재생성 (재실행 시 중복 방지)
    try:
        client.delete_collection(name)
    except Exception:
        pass

    collection = client.create_collection(name=name, embedding_function=embed_fn)

    ids, documents, metadatas = [], [], []
    for c in chunks:
        ids.append(c["metadata"]["id"])
        documents.append(c["page_content"])
        # Chroma는 메타데이터 값으로 str/int/float/bool만 허용 → None 제거
        meta = {k: v for k, v in c["metadata"].items() if v is not None}
        metadatas.append(meta)

    total = len(ids)
    for i in range(0, total, BATCH_SIZE):
        collection.add(
            ids=ids[i:i + BATCH_SIZE],
            documents=documents[i:i + BATCH_SIZE],
            metadatas=metadatas[i:i + BATCH_SIZE],
        )
        done = min(i + BATCH_SIZE, total)
        print(f"    {done}/{total} 청크 임베딩 완료", end="\r")
        time.sleep(0.1)          # API 레이트리밋 여유

    print(f"    {total}/{total} 청크 임베딩 완료 ✓        ")
    return collection


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="특정 전략만 구축 (예: S5_recursive_ko)")
    args = parser.parse_args()

    with open(INPUT_PATH, encoding="utf-8") as f:
        docs = json.load(f)
    print(f"입력 문서: {len(docs)}건\n")

    embed_fn = get_embedding_function()
    client = chromadb.PersistentClient(path=DB_PATH)

    targets = {args.only: STRATEGIES[args.only]} if args.only else STRATEGIES

    summary = []
    for key, (desc, fn) in targets.items():
        print(f"▶ {key} — {desc}")
        chunks = fn(docs)
        print(f"    청크 {len(chunks)}개 생성")
        build_collection(client, key, chunks, embed_fn)
        summary.append((key, desc, len(chunks)))
        print()

    print("=" * 60)
    print("  DB 구축 완료")
    print("=" * 60)
    for key, desc, n in summary:
        print(f"  {key:<18} {n:>6} 청크   {desc}")
    print(f"\n  저장 위치: {DB_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    main()
