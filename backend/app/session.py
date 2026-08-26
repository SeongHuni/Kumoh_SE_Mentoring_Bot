"""대화 이력 관리.

PROMPT_STRATEGY.md 의 입력 계약을 그대로 구현한다.

  - 같은 세션의 최근 3개 '완료된' 대화쌍만 사용한다
  - 총 길이는 1,200 토큰 이내로 제한하고, 넘으면 오래된 쌍부터 버린다
  - LLM이 만든 자유 형식 요약으로 대체하지 않는다
    (요약 과정에서 사실이 왜곡될 수 있다)
  - 대화 본문은 untrusted 경계 안에 role 과 turn ID 를 보존해 넣는다

(Node 판 scripts/lib/session.js 를 옮긴 것이다.)
"""

from __future__ import annotations

from dataclasses import dataclass, field

MAX_PAIRS = 3
MAX_TOKENS = 1200


def estimate_token_count(text: str) -> int:
    """Node 판 chunking-common.js 의 estimateTokenCount 와 같은 추정식.

    한글은 글자당 약 1.4 토큰, 그 외는 4 글자당 1 토큰으로 잡는다.
    정확한 토크나이저가 아니라 예산을 지키기 위한 근사치다.
    """
    if not text:
        return 0
    hangul = sum(1 for ch in text if "가" <= ch <= "힣")
    rest = len(text) - hangul
    return int(hangul * 1.4 + rest / 4) + 1


def _escape_xml(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@dataclass
class Pair:
    user: str
    assistant: str


@dataclass
class Session:
    max_pairs: int = MAX_PAIRS
    max_tokens: int = MAX_TOKENS
    pairs: list[Pair] = field(default_factory=list)

    def add_pair(self, user_text: str, assistant_text: str) -> None:
        """답변까지 끝난 한 쌍만 이력에 넣는다. 답변이 없는 턴은 '완료'가 아니다."""
        if not user_text or not assistant_text:
            return
        self.pairs.append(Pair(user=str(user_text), assistant=str(assistant_text)))
        if len(self.pairs) > self.max_pairs:
            self.pairs = self.pairs[-self.max_pairs:]

    def reset(self) -> None:
        self.pairs = []

    def recent_pairs(self) -> list[Pair]:
        """토큰 예산에 맞게 오래된 쌍부터 잘라낸 목록."""
        kept: list[Pair] = []
        total = 0
        # 최신 쌍부터 담아야 오래된 것이 먼저 밀려난다.
        for pair in reversed(self.pairs):
            cost = estimate_token_count(pair.user) + estimate_token_count(pair.assistant)
            if total + cost > self.max_tokens and kept:
                break
            kept.insert(0, pair)
            total += cost
        return kept

    def to_prompt_block(self) -> str:
        """검색 계획기에 넣을 블록.

        대화 내용은 데이터일 뿐 지시가 아니라는 것을 untrusted 속성과
        태그 구조로 명시한다.
        """
        pairs = self.recent_pairs()
        if not pairs:
            return '<conversation_history untrusted="true" count="0" />'

        turns = []
        for i, pair in enumerate(pairs, start=1):
            n = f"{i:02d}"
            turns.append(
                f'<turn id="u-{n}" role="user">{_escape_xml(pair.user)}</turn>\n'
                f'<turn id="a-{n}" role="assistant">{_escape_xml(pair.assistant)}</turn>'
            )

        return (
            f'<conversation_history untrusted="true" max_exchanges="{self.max_pairs}" '
            f'max_tokens="{self.max_tokens}" count="{len(pairs)}">\n'
            + "\n".join(turns)
            + "\n</conversation_history>"
        )
