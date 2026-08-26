"""검색 점수 보정과 결과 후처리.

두 가지를 한다.

  1. 중요도 가중치 — 최종 점수 = 유사도 + 이벤트 가중치 − 경과연수 감쇠
  2. 후처리        — 비슷한 것 중 최신 우선(preferRecentAmongSimilar), 다양성(diversify)

[왜 이벤트 가중치가 필요한가]
임베딩은 "학과에서 이게 제일 중요한 공지"라는 걸 모른다. 그건 데이터에 없는
사람의 지식이다. 실제로 이정연 장학금은 학과 대표 장학금인데
"장학금 신청 조건" 질의에서 주제 기준 8위(0.500)까지 밀렸다.
석사우수장학금 공지에는 "백분위 87점 이상" 같은 조건 문구가 빽빽한 반면
이정연 공지는 서술형이라 표면적으로 덜 닮았기 때문이다.

[왜 시간 감쇠가 같이 필요한가]
이벤트 가중치만 주면 같은 이벤트의 과거 공지가 전부 함께 올라온다.
실제로 +0.1을 줬을 때 top-5 중 4자리를 이정연이 차지했고 그중 3개가
2024~2025년 공지였다. 그래서 오래된 문서는 소폭 감점한다.

[왜 후처리가 필요한가]
이 코퍼스는 매년 반복되는 공지가 많다(연도·학기만 다른 동일 제목 문서가 30%).
  - 철 지난 답: "수강지도 상담 언제야"에 2024년 공지가 먼저 잡힌다
  - 결과 쏠림: "장학금 신청 조건" top-20 에 외국어성적우수장학금 청크가 17개

(Node 판 scripts/lib/importance.js + retrieval-postprocess.js 를 옮긴 것이다.)
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Sequence

DEFAULT_RECENCY = {"decay_per_year": 0.012, "max_decay": 0.04}

# 유사도가 사실상 구분되지 않는 폭.
# 측정 근거: 300문항에서 상위 1위와 5위의 유사도 차이 중앙값이 0.045였고,
# 55.3%의 질문이 상위 5개가 0.05 이내로 몰려 있었다.
SIMILAR_MARGIN = float(os.getenv("RAG_SIMILAR_MARGIN", "0.05"))


@dataclass
class ScoringConfig:
    rules: list[dict[str, Any]] = field(default_factory=list)
    recency: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_RECENCY))


def load_scoring_config(path: Path) -> ScoringConfig:
    if not path.exists():
        return ScoringConfig()
    parsed = json.loads(path.read_text(encoding="utf-8"))
    rules = [
        rule
        for rule in (parsed.get("rules") or [])
        if rule and rule.get("match") and isinstance(rule.get("boost"), (int, float))
    ]
    recency = dict(DEFAULT_RECENCY)
    recency.update(parsed.get("recency") or {})
    return ScoringConfig(rules=rules, recency=recency)


def _matches(rule: dict[str, Any], metadata: dict[str, Any]) -> bool:
    """규칙의 match 조건이 '모두' 맞아야 적용. title 은 부분 일치, 나머지는 정확히 일치."""
    match = rule.get("match") or {}
    if not match:
        return False
    if match.get("title") and match["title"] not in str(metadata.get("title") or ""):
        return False
    for key in ("original_id", "category", "source"):
        if match.get(key) and metadata.get(key) != match[key]:
            return False
    return True


def boost_for(metadata: dict[str, Any], rules: Sequence[dict[str, Any]]) -> float:
    """여러 규칙에 걸리면 가장 큰 값 하나만 쓴다. 더하면 특정 문서가 과도하게 올라간다."""
    best = 0.0
    for rule in rules:
        if _matches(rule, metadata):
            best = max(best, float(rule["boost"]))
    return best


def _years_since(published_ts: Any, today: date) -> float | None:
    """published_ts(YYYYMMDD) 기준 경과 연수. 날짜가 없으면 None."""
    text = str(published_ts or "")
    if not re.fullmatch(r"\d{8}", text):
        return None
    try:
        published = datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None
    return max(0.0, (today - published).days / 365.25)


def decay_for(metadata: dict[str, Any], recency: dict[str, float], today: date) -> float:
    years = _years_since(metadata.get("published_ts"), today)
    if years is None:
        # 날짜가 없으면 감쇠하지 않는다. 강의평과 학사 FAQ 가 여기 해당한다.
        # 상시 정보라 늙지 않는 편이 맞다.
        return 0.0
    return min(recency["max_decay"], years * recency["decay_per_year"])


def apply_scoring(results: list, config: ScoringConfig, today: date | None = None) -> list:
    """검색 결과에 보정을 적용하고 다시 정렬한다.

    원래 유사도는 base_score 로 남겨 무엇이 왜 움직였는지 확인할 수 있게 한다.
    results 의 각 항목은 .metadata(dict) 와 .score(float) 를 가져야 한다.
    """
    today = today or date.today()
    if not config.rules and not config.recency.get("decay_per_year"):
        return results

    for item in results:
        metadata = item.metadata or {}
        boost = boost_for(metadata, config.rules)
        decay = decay_for(metadata, config.recency, today)
        if not boost and not decay:
            continue
        item.base_score = item.score
        item.score = item.score + boost - decay
        item.boost = boost
        item.decay = decay

    return sorted(results, key=lambda r: r.score, reverse=True)


# ------------------------------------------------------------------ 후처리
def topic_key(title: str) -> str:
    """"연도·학기만 다른 같은 공지"를 한 주제로 묶는 키.

    괄호 안 부연설명과 숫자를 지우고 기호를 정리한다.
    대괄호는 남긴다 — "[이정연 장학금]"처럼 장학금 이름이 들어있어서,
    지우면 서로 다른 장학금이 한 주제로 뭉쳐버린다.
    """
    text = re.sub(r"\([^)]*\)", " ", str(title or ""))
    text = re.sub(r"\d+", "", text)
    text = re.sub(r"[~\-–—/.,:]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _published_ts(item) -> int:
    try:
        return int((item.metadata or {}).get("published_ts"))
    except (TypeError, ValueError):
        return -1


def prefer_recent_among_similar(results: list, k: int, margin: float = SIMILAR_MARGIN) -> list:
    """관련도가 비슷한 후보끼리는 게시일이 늦은 것을 앞으로 보낸다.

    관련도가 확실히 낮은 것은 순서를 건드리지 않는다 — 최신이라는 이유로
    엉뚱한 문서가 올라오면 안 되기 때문이다.
    """
    if not results:
        return []

    top = results[0].score
    similar = [r for r in results if top - r.score <= margin]
    rest = [r for r in results if top - r.score > margin]
    similar.sort(key=_published_ts, reverse=True)
    return (similar + rest)[:k]


def diversify(results: list, k: int, max_per_doc: int = 2, max_per_topic: int = 2) -> list:
    """top-k 를 고를 때 두 가지 상한을 함께 건다.

    max_per_topic — 같은 주제(연도만 다른 반복 공지 묶음)가 차지할 수 있는 최대 자리.
                    이게 없으면 공지가 많은 제도 하나가 top-k 를 독차지한다.
    max_per_doc   — 한 문서에서 가져올 최대 청크 수.
                    1 로 조이면 긴 공지에 답이 흩어진 질문에서 근거가 잘려 답변이 얕아진다.
                    2 면 깊이를 남기면서 독차지도 막는다.
    """
    doc_count: dict[str, int] = {}
    topic_count: dict[str, int] = {}
    picked: list = []
    skipped: list = []

    for item in results:
        metadata = item.metadata or {}
        doc = metadata.get("original_id")
        topic = topic_key(metadata.get("title"))

        if (doc and doc_count.get(doc, 0) >= max_per_doc) or (
            topic and topic_count.get(topic, 0) >= max_per_topic
        ):
            skipped.append(item)
            continue

        if doc:
            doc_count[doc] = doc_count.get(doc, 0) + 1
        if topic:
            topic_count[topic] = topic_count.get(topic, 0) + 1
        picked.append(item)
        if len(picked) == k:
            return picked

    # 후보가 부족하면 상한 때문에 뺐던 것으로 채운다.
    # "다양성 때문에 결과가 줄어드는" 상황을 막기 위한 안전장치다.
    return (picked + skipped)[:k]
