// 검색 결과 후처리.
//
// 이 코퍼스는 매년 반복되는 공지가 많다(연도·학기만 다른 동일 제목 문서가 30%).
// 그래서 두 가지 문제가 생긴다.
//
//  1. 철 지난 답  — "수강지도 상담 언제야"에 2024년 공지가 먼저 잡힌다
//  2. 결과 쏠림   — "장학금 신청 조건" top-20에 외국어성적우수장학금 청크가 17개 들어차
//                   이정연 장학금 등 다른 장학금이 33위까지 밀린다
//
// 1은 preferRecentAmongSimilar, 2는 diversify 가 처리한다.

// 유사도가 사실상 구분되지 않는 폭.
// 측정 근거: 300문항에서 상위 1위와 5위의 유사도 차이 중앙값이 0.045였고,
// 55.3%의 질문이 상위 5개가 0.05 이내로 몰려 있었다.
const SIMILAR_MARGIN = Number(process.env.RAG_SIMILAR_MARGIN || 0.05);

function publishedTs(r) {
  const v = Number(r?.metadata?.published_ts);
  return Number.isFinite(v) ? v : -1;
}

// "연도·학기만 다른 같은 공지"를 한 주제로 묶는 키.
//
// 괄호 안 부연설명과 숫자를 지우고 기호를 정리한다.
// 대괄호는 남긴다 — "[이정연 장학금]"처럼 장학금 이름이 들어있어서,
// 지우면 서로 다른 장학금이 한 주제로 뭉쳐버린다.
function topicKey(title) {
  return String(title || "")
    .replace(/\([^)]*\)/gu, " ")
    .replace(/\d+/gu, "")
    .replace(/[~\-–—/.,:]+/gu, " ")
    .replace(/\s+/gu, " ")
    .trim();
}

// 관련도가 비슷한 후보끼리는 게시일이 늦은 것을 앞으로 보낸다.
// 관련도가 확실히 낮은 것은 순서를 건드리지 않는다 — 최신이라는 이유로
// 엉뚱한 문서가 올라오면 안 되기 때문이다.
function preferRecentAmongSimilar(results, k, margin = SIMILAR_MARGIN) {
  if (!results.length) return [];

  const top = results[0].score;
  const similar = [];
  const rest = [];

  for (const r of results) {
    (top - r.score <= margin ? similar : rest).push(r);
  }

  similar.sort((a, b) => publishedTs(b) - publishedTs(a));
  return [...similar, ...rest].slice(0, k);
}

// top-k를 고를 때 두 가지 상한을 함께 건다.
//
//  maxPerTopic — 같은 주제(연도만 다른 반복 공지 묶음)가 차지할 수 있는 최대 자리.
//                이게 없으면 공지가 많은 제도 하나가 top-k를 독차지한다.
//  maxPerDoc   — 한 문서에서 가져올 최대 청크 수.
//                1로 조이면 긴 공지에 답이 흩어진 질문에서 근거가 잘려 답변이 얕아진다.
//                2면 깊이를 남기면서 독차지도 막는다.
//
// 순위가 높은 것부터 훑으며 상한에 걸리는 것만 건너뛴다. 상한에 걸려 자리가
// 남으면 다음 순위가 채우므로, 결과 수는 최대한 k에 맞춘다.
function diversify(results, k, { maxPerDoc = 2, maxPerTopic = 2 } = {}) {
  const docCount = new Map();
  const topicCount = new Map();
  const picked = [];
  const skipped = [];

  for (const r of results) {
    const doc = r.metadata?.original_id;
    const topic = topicKey(r.metadata?.title);

    const docOver = doc && (docCount.get(doc) || 0) >= maxPerDoc;
    const topicOver = topic && (topicCount.get(topic) || 0) >= maxPerTopic;

    if (docOver || topicOver) {
      skipped.push(r);
      continue;
    }

    if (doc) docCount.set(doc, (docCount.get(doc) || 0) + 1);
    if (topic) topicCount.set(topic, (topicCount.get(topic) || 0) + 1);
    picked.push(r);
    if (picked.length === k) return picked;
  }

  // 후보가 부족하면 상한 때문에 뺐던 것으로 채운다.
  // "다양성 때문에 결과가 줄어드는" 상황을 막기 위한 안전장치다.
  return [...picked, ...skipped].slice(0, k);
}

module.exports = { preferRecentAmongSimilar, diversify, topicKey, SIMILAR_MARGIN };
