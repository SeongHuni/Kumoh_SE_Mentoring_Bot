// Chroma에 적재된 컬렉션을 골든셋으로 재평가한다.
// eval-retrieval.js는 메모리에서 '정확한' 코사인 전수 계산을 하지만 Chroma는 HNSW 근사 검색이므로,
// 리포트에 적은 수치가 실제 배포 구성에서도 성립하는지 확인하는 용도다.
const fs = require("fs");
const path = require("path");
const { ROOT, readApiKey, readJsonl, embedQuery } = require("./lib/rag-core");
const { openCollection, search, COLLECTION } = require("./lib/chroma-store");

const GOLDEN_FILE = path.join(ROOT, "outputs", "golden_set", "golden_questions.jsonl");
const RESULTS_DIR = path.join(ROOT, "outputs", "eval_results");
const K = 5;

const mean = (values) => (values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0);

function percentile(values, p) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor((sorted.length - 1) * p)];
}

async function main() {
  const questions = readJsonl(GOLDEN_FILE);
  const apiKey = readApiKey();
  const collection = await openCollection();

  console.log(`컬렉션 '${COLLECTION}'을 골든셋 ${questions.length}문항으로 평가합니다...`);

  const rows = [];
  const latencies = [];

  for (const q of questions) {
    const queryEmbedding = await embedQuery(apiKey, q.question);

    const start = process.hrtime.bigint();
    const retrieved = await search(collection, queryEmbedding, K);
    latencies.push(Number(process.hrtime.bigint() - start) / 1e6);

    const goldSet = new Set(q.gold_doc_ids);
    const hits = retrieved.map((r) => goldSet.has(r.metadata.original_id));
    const firstHit = hits.findIndex(Boolean);

    rows.push({
      question: q.question,
      gold_doc_ids: q.gold_doc_ids,
      top3Hit: hits.slice(0, 3).some(Boolean) ? 1 : 0,
      top5Hit: hits.some(Boolean) ? 1 : 0,
      rr5: firstHit === -1 ? 0 : 1 / (firstHit + 1),
      contextPrecision5: hits.filter(Boolean).length / K,
      retrieved: retrieved.map((r) => ({
        chunk_id: r.chunk_id,
        original_id: r.metadata.original_id,
        score: r.score,
      })),
    });
  }

  const summary = {
    backend: "chroma",
    collection: COLLECTION,
    recall_at_3: mean(rows.map((r) => r.top3Hit)),
    recall_at_5: mean(rows.map((r) => r.top5Hit)),
    mrr_at_5: mean(rows.map((r) => r.rr5)),
    context_precision_at_5: mean(rows.map((r) => r.contextPrecision5)),
    mean_latency_ms: mean(latencies),
    p90_latency_ms: percentile(latencies, 0.9),
    question_count: questions.length,
    evaluated_at: new Date().toISOString(),
  };

  fs.mkdirSync(RESULTS_DIR, { recursive: true });
  fs.writeFileSync(
    path.join(RESULTS_DIR, "chroma_retrieval.json"),
    `${JSON.stringify(summary, null, 2)}\n`,
    "utf8"
  );
  fs.writeFileSync(
    path.join(RESULTS_DIR, "chroma_retrieval_raw.jsonl"),
    rows.map((r) => JSON.stringify(r)).join("\n") + "\n",
    "utf8"
  );

  // 메모리 기반 D_500 결과와 나란히 보여준다.
  const inMemory = JSON.parse(
    fs.readFileSync(path.join(RESULTS_DIR, "retrieval_leaderboard.json"), "utf8")
  ).find((row) => row.experiment === "D_500");

  console.log("\n=== D_500: 메모리(정확 검색) vs Chroma(HNSW) ===");
  const compare = (label, a, b) =>
    console.log(`${label.padEnd(22)} ${a.toFixed(3).padStart(7)} ${b.toFixed(3).padStart(9)}   ${(b - a >= 0 ? "+" : "") + (b - a).toFixed(3)}`);
  console.log(`${"".padEnd(22)} ${"메모리".padStart(6)} ${"Chroma".padStart(8)}   차이`);
  compare("Recall@3", inMemory.recall_at_3, summary.recall_at_3);
  compare("Recall@5", inMemory.recall_at_5, summary.recall_at_5);
  compare("MRR@5", inMemory.mrr_at_5, summary.mrr_at_5);
  compare("ContextPrecision@5", inMemory.context_precision_at_5, summary.context_precision_at_5);
  // 지표 숫자보다 중요한 건 "LLM에 실제로 들어가는 컨텍스트가 같은가"다.
  // 순위가 한 칸 밀려도 top-k 집합이 같으면 생성 결과에는 영향이 없다.
  const memoryRaw = readJsonl(path.join(RESULTS_DIR, "retrieval_raw.jsonl")).filter(
    (r) => r.experiment === "D_500"
  );
  let sameSet = 0;
  let sameOrder = 0;
  for (let i = 0; i < rows.length && i < memoryRaw.length; i += 1) {
    const a = memoryRaw[i].retrieved.map((r) => r.chunk_id);
    const b = rows[i].retrieved.map((r) => r.chunk_id);
    if (JSON.stringify(a) === JSON.stringify(b)) sameOrder += 1;
    if (JSON.stringify([...a].sort()) === JSON.stringify([...b].sort())) sameSet += 1;
  }
  console.log(`\ntop-${K} 청크 집합 일치: ${sameSet}/${rows.length}문항 (순서까지 일치: ${sameOrder})`);

  console.log(
    `검색 지연: 메모리 ${inMemory.mean_latency_ms.toFixed(2)}ms → Chroma ${summary.mean_latency_ms.toFixed(2)}ms (HTTP 왕복 포함)`
  );
  console.log(`저장: ${path.relative(ROOT, path.join(RESULTS_DIR, "chroma_retrieval.json"))}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
