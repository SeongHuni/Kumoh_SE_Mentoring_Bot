// 추천 질문 풀의 답변 품질을 채점한다.
//
//   node grade_pool.js            현재 풀 전체
//   node grade_pool.js "질문1" "질문2" ...   지정한 질문만
//
// 좋은 추천 질문의 조건 (거부만 안 하면 되는 게 아니다)
//   - response_type 이 answer 다 (되묻기·범위밖이 아님)
//   - 거부 문구로 시작하지 않는다
//   - 인용 표기 [N] 이 있다. 근거 없이 쓴 답은 신뢰할 수 없다
//   - 답이 너무 짧지 않다. 한 줄짜리는 추천 질문으로 약하다
//   - "확인할 수 없습니다" 가 본문 중간에 섞이지 않는다 (반쪽 답변)
const fs = require("fs");

const API = "http://localhost:8787/api/chat";

async function ask(question) {
  const res = await fetch(API, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: `grade-${Math.random()}` }),
  });
  return res.json();
}

function grade(question, payload) {
  const answer = (payload.answer || "").trim();
  const first = answer.split("\n")[0];
  const citations = [...answer.matchAll(/\[(?:자료\s*)?\d{1,2}\]/gu)].length;
  const partial = /확인할 수 없|찾지 못했|찾을 수 없/.test(answer);
  const problems = [];

  if (payload.response_type !== "answer") problems.push(payload.response_type);
  if (/확인할 수 없|찾지 못했|찾을 수 없/.test(first) && answer.length < 200) {
    problems.push("거부");
  } else if (partial) {
    problems.push("부분거부");
  }
  if (citations === 0) problems.push("인용없음");
  if (answer.length < 60) problems.push(`짧음(${answer.length}자)`);

  return {
    question,
    ok: problems.length === 0,
    problems,
    citations,
    length: answer.length,
    sources: (payload.sources || []).length,
    preview: answer.replace(/\n/g, " ").slice(0, 70),
  };
}

function loadPool() {
  const src = fs.readFileSync("backend/app/suggestions.py", "utf8");
  const block = src.slice(
    src.indexOf("SUGGESTED_POOL"),
    src.indexOf("SUGGESTED_TOPICS"),
  );
  const pool = {};
  let topic = null;
  for (const line of block.split("\n")) {
    const topicMatch = line.match(/^\s{4}"([^"]+)":\s*\[/u);
    if (topicMatch) {
      topic = topicMatch[1];
      pool[topic] = [];
      continue;
    }
    const itemMatch = line.match(/^\s{8}"([^"]+)",/u);
    if (itemMatch && topic) pool[topic].push(itemMatch[1]);
  }
  return pool;
}

(async () => {
  const argv = process.argv.slice(2);
  let entries;

  if (argv.length) {
    entries = argv.map((q) => ["(지정)", q]);
  } else {
    const pool = loadPool();
    entries = [];
    for (const [topic, questions] of Object.entries(pool)) {
      for (const q of questions) entries.push([topic, q]);
    }
  }

  const results = [];
  for (const [topic, question] of entries) {
    let payload;
    try {
      payload = await ask(question);
    } catch (error) {
      results.push({ topic, question, ok: false, problems: ["요청실패"], preview: "" });
      continue;
    }
    results.push({ topic, ...grade(question, payload) });
  }

  const bad = results.filter((r) => !r.ok);
  const good = results.filter((r) => r.ok);

  console.log(`\n총 ${results.length}개 · 양호 ${good.length} · 문제 ${bad.length}\n`);

  if (bad.length) {
    console.log("=== 문제 있는 질문 ===");
    for (const r of bad) {
      console.log(`  [${r.problems.join(",")}] ${r.question}`);
      console.log(`      ${r.preview}`);
    }
    console.log();
  }

  console.log("=== 양호 (인용 수 / 길이) ===");
  for (const r of good) {
    console.log(`  [${String(r.citations).padStart(2)}인용 ${String(r.length).padStart(4)}자] ${r.question}`);
  }

  fs.writeFileSync("pool_grades.json", JSON.stringify(results, null, 2), "utf8");
})();
