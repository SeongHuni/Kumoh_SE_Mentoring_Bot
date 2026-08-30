// outputs/eval_results/natural_questions.py 의 질문으로 현재 배포된 파이프라인을
// 다시 잰다. Recall@k 가 아니라 "그럴듯하게 지어내지 않고 자료 기반으로
// 답하는가"를 잰다 — 정답 문서 ID가 없어서 그 이상은 잴 수 없다.
//
//   node scripts/measure_natural.js
const fs = require("fs");

const API = "http://localhost:8787/api/chat";

function loadQuestions() {
  const src = fs.readFileSync("outputs/eval_results/natural_questions.py", "utf8");
  const start = src.indexOf("QUESTIONS: list");
  const body = src.slice(src.indexOf("[", start), src.lastIndexOf("]") + 1);
  // (질문, 기대판정, SEQ, 비고) 튜플을 정규식으로 뽑는다. 파이썬 리터럴을
  // 굳이 파싱하지 않고 형태가 고정돼 있다는 걸 이용한다.
  const rows = [];
  const re = /\(\s*"((?:[^"\\]|\\.)*)"\s*,\s*"(answer|no_answer)"\s*,\s*"([^"]*)"\s*,\s*"((?:[^"\\]|\\.)*)"\s*\)/gu;
  let m;
  while ((m = re.exec(body))) {
    rows.push({ question: m[1], expect: m[2], seq: m[3], note: m[4] });
  }
  return rows;
}

async function ask(question) {
  const res = await fetch(API, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: `nat-${Math.random()}` }),
  });
  return res.json();
}

function isRefusal(answer) {
  const first = (answer || "").trim().split("\n")[0];
  return (/확인할 수 없|찾지 못했|찾을 수 없|범위 안에서만 답변/.test(first)) && answer.length < 200;
}

(async () => {
  const rows = loadQuestions();
  console.log(`문항 ${rows.length}개 (양성 ${rows.filter(r => r.expect === "answer").length} · 음성 ${rows.filter(r => r.expect === "no_answer").length})\n`);

  const results = [];
  for (const row of rows) {
    let payload;
    try {
      payload = await ask(row.question);
    } catch (e) {
      results.push({ ...row, ok: false, got: "요청실패" });
      continue;
    }
    const refused = isRefusal(payload.answer);
    const gotType = payload.response_type === "clarification" ? "clarification" : (refused ? "no_answer" : "answer");
    const ok = gotType === row.expect || (row.expect === "answer" && gotType === "clarification");
    const citations = [...(payload.answer || "").matchAll(/\[(?:자료\s*)?\d{1,2}\]/gu)].length;
    results.push({ ...row, ok, got: gotType, citations, length: (payload.answer || "").length, preview: (payload.answer || "").replace(/\n/g, " ").slice(0, 60) });
  }

  const positives = results.filter(r => r.expect === "answer");
  const negatives = results.filter(r => r.expect === "no_answer");
  const posOk = positives.filter(r => r.ok);
  const negOk = negatives.filter(r => r.ok);
  const cited = positives.filter(r => r.ok && r.citations > 0);

  console.log("=== 양성 문항 중 문제 (기대: 답변) ===");
  for (const r of positives.filter(r => !r.ok)) {
    console.log(`  [${r.got}] ${r.question}  (${r.seq})`);
    console.log(`      ${r.preview}`);
  }
  console.log("\n=== 음성 문항 중 문제 (기대: 거부·범위밖인데 답을 지어냄) ===");
  for (const r of negatives.filter(r => !r.ok)) {
    console.log(`  [${r.got}] ${r.question}  (${r.seq})`);
    console.log(`      ${r.preview}`);
  }

  console.log("\n=== 요약 ===");
  console.log(`  양성 ${positives.length}건 중 정상 응답 ${posOk.length}건 (${(100 * posOk.length / positives.length).toFixed(1)}%)`);
  console.log(`  양성 중 인용까지 붙은 것 ${cited.length}/${positives.length}건`);
  console.log(`  음성 ${negatives.length}건 중 올바르게 거부 ${negOk.length}건 (${(100 * negOk.length / negatives.length).toFixed(1)}%)`);

  fs.writeFileSync("outputs/eval_results/natural_questions_result.json", JSON.stringify(results, null, 2), "utf8");
  console.log("\n  -> outputs/eval_results/natural_questions_result.json");
})();
