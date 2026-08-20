// 대화 이력 관리.
//
// PROMPT_STRATEGY.md의 입력 계약을 그대로 구현한다.
//  - 같은 세션의 최근 3개 '완료된' 대화쌍만 사용한다
//  - 총 길이는 1,200 토큰 이내로 제한하고, 넘으면 오래된 쌍부터 버린다
//  - LLM이 만든 자유 형식 요약으로 대체하지 않는다 (요약 과정에서 사실이 왜곡될 수 있으므로)
//  - 대화 본문은 untrusted 경계 안에 role과 turn ID를 보존해 넣는다
const { estimateTokenCount } = require("./chunking-common");

const MAX_PAIRS = 3;
const MAX_TOKENS = 1200;

class Session {
  constructor({ maxPairs = MAX_PAIRS, maxTokens = MAX_TOKENS } = {}) {
    this.maxPairs = maxPairs;
    this.maxTokens = maxTokens;
    this.pairs = []; // { user, assistant }
  }

  // 답변까지 끝난 한 쌍만 이력에 넣는다. 답변이 없는 턴은 '완료'가 아니다.
  addPair(userText, assistantText) {
    if (!userText || !assistantText) return;
    this.pairs.push({ user: String(userText), assistant: String(assistantText) });
    if (this.pairs.length > this.maxPairs) {
      this.pairs = this.pairs.slice(-this.maxPairs);
    }
  }

  reset() {
    this.pairs = [];
  }

  get length() {
    return this.pairs.length;
  }

  // 토큰 예산에 맞게 오래된 쌍부터 잘라낸 목록을 돌려준다.
  recentPairs() {
    const kept = [];
    let total = 0;

    // 최신 쌍부터 담아야 오래된 것이 먼저 밀려난다.
    for (let i = this.pairs.length - 1; i >= 0; i -= 1) {
      const p = this.pairs[i];
      const cost = estimateTokenCount(p.user) + estimateTokenCount(p.assistant);
      if (total + cost > this.maxTokens && kept.length) break;
      kept.unshift(p);
      total += cost;
    }
    return kept;
  }

  // 검색 계획기에 넣을 블록. 대화 내용은 데이터일 뿐 지시가 아니라는 것을
  // untrusted 속성과 태그 구조로 명시한다.
  toPromptBlock() {
    const pairs = this.recentPairs();
    if (!pairs.length) {
      return '<conversation_history untrusted="true" count="0" />';
    }

    const turns = pairs
      .map((p, i) => {
        const n = String(i + 1).padStart(2, "0");
        return (
          `<turn id="u-${n}" role="user">${escapeXml(p.user)}</turn>\n` +
          `<turn id="a-${n}" role="assistant">${escapeXml(p.assistant)}</turn>`
        );
      })
      .join("\n");

    return (
      `<conversation_history untrusted="true" max_exchanges="${this.maxPairs}" ` +
      `max_tokens="${this.maxTokens}" count="${pairs.length}">\n${turns}\n</conversation_history>`
    );
  }

  // 어떤 턴을 실제로 넘겼는지 기록용 (사후 검증에 쓴다)
  turnIds() {
    return this.recentPairs().flatMap((_, i) => {
      const n = String(i + 1).padStart(2, "0");
      return [`u-${n}`, `a-${n}`];
    });
  }
}

function escapeXml(text) {
  return String(text)
    .replace(/&/gu, "&amp;")
    .replace(/</gu, "&lt;")
    .replace(/>/gu, "&gt;");
}

module.exports = { Session, MAX_PAIRS, MAX_TOKENS };
