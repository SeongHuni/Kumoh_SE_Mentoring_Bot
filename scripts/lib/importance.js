// 검색 점수 보정 — 이벤트 가중치 + 시간 감쇠.
//
//   최종 점수 = 유사도 + 이벤트 가중치 − 경과연수 감쇠
//
// [왜 이벤트 가중치가 필요한가]
// 임베딩은 "학과에서 이게 제일 중요한 공지"라는 걸 모른다. 그건 데이터에 없는
// 사람의 지식이다. 실제로 이정연 장학금은 학과 대표 장학금인데
// "장학금 신청 조건" 질의에서 주제 기준 8위(0.500)까지 밀렸다.
// 석사우수장학금 공지에는 "백분위 87점 이상" 같은 조건 문구가 빽빽한 반면
// 이정연 공지는 서술형이라 표면적으로 덜 닮았기 때문이다.
//
// [왜 시간 감쇠가 같이 필요한가]
// 이벤트 가중치만 주면 같은 이벤트의 과거 공지가 전부 함께 올라온다.
// 실제로 +0.1을 줬을 때 top-5 중 4자리를 이정연이 차지했고 그중 3개가
// 2024~2025년 공지였다. 최신 신청 안내가 아니라 옛날 수여식 공지가 올라온 것이다.
// 그래서 오래된 문서는 소폭 감점해 같은 이벤트 안에서 최신이 앞서게 한다.
const fs = require("fs");
const path = require("path");

const CONFIG_FILE = path.join(process.cwd(), "data", "importance.json");

const DEFAULT_RECENCY = { decay_per_year: 0.012, max_decay: 0.04 };

function loadConfig(file = CONFIG_FILE) {
  if (!fs.existsSync(file)) return { rules: [], recency: DEFAULT_RECENCY };
  const parsed = JSON.parse(fs.readFileSync(file, "utf8"));
  return {
    rules: (parsed.rules || []).filter((r) => r && r.match && Number.isFinite(Number(r.boost))),
    recency: { ...DEFAULT_RECENCY, ...(parsed.recency || {}) },
  };
}

// 규칙의 match 조건이 '모두' 맞아야 적용한다. title 은 부분 일치, 나머지는 정확히 일치.
function matches(rule, metadata = {}) {
  const m = rule.match || {};
  if (m.title && !String(metadata.title || "").includes(m.title)) return false;
  if (m.original_id && metadata.original_id !== m.original_id) return false;
  if (m.category && metadata.category !== m.category) return false;
  if (m.source && metadata.source !== m.source) return false;
  return Object.keys(m).length > 0;
}

// 여러 규칙에 걸리면 가장 큰 값 하나만 쓴다. 더하면 특정 문서가 과도하게 올라간다.
function boostFor(metadata, rules) {
  let best = 0;
  const hit = [];
  for (const r of rules) {
    if (!matches(r, metadata)) continue;
    hit.push(r.name || "(이름없음)");
    best = Math.max(best, Number(r.boost));
  }
  return { boost: best, names: hit };
}

// published_ts(YYYYMMDD 정수) 기준 경과 연수. 날짜가 없으면 감쇠하지 않는다.
function yearsSince(publishedTs, today) {
  const s = String(publishedTs || "");
  if (!/^\d{8}$/u.test(s)) return null;
  const d = new Date(`${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`);
  if (Number.isNaN(d.getTime())) return null;
  return Math.max(0, (today - d) / (365.25 * 24 * 3600 * 1000));
}

function decayFor(metadata, recency, today) {
  const years = yearsSince(metadata?.published_ts, today);
  if (years === null) return 0;
  return Math.min(recency.max_decay, years * recency.decay_per_year);
}

// 검색 결과에 보정을 적용하고 다시 정렬한다.
// 원래 유사도는 base_score 로 남겨 무엇이 왜 움직였는지 확인할 수 있게 한다.
function applyScoring(results, config, today = new Date()) {
  const { rules, recency } = config;
  if (!rules.length && !recency.decay_per_year) return results;

  return results
    .map((r) => {
      const { boost, names } = boostFor(r.metadata, rules);
      const decay = decayFor(r.metadata, recency, today);
      if (!boost && !decay) return r;
      return {
        ...r,
        base_score: r.score,
        score: r.score + boost - decay,
        boost,
        decay,
        boost_rules: names,
      };
    })
    .sort((a, b) => b.score - a.score);
}

module.exports = { loadConfig, applyScoring, boostFor, decayFor, CONFIG_FILE };
