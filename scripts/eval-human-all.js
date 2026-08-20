// manifest의 모든 청킹 실험을 사람 작성 300문항으로 재평가한다.
//   node scripts/eval-human-all.js
//
// 목적: 1차 발표의 전략 간 순위가 LLM 생성 골든셋의 편향(제목 유출) 때문에
// 왜곡된 것인지 확인한다. 질문 임베딩은 디스크 캐시를 쓰므로 재실행 비용이 없다.
const fs = require("fs");
const path = require("path");
const {
  ROOT,
  readApiKey,
  embedQuery,
  loadExperimentRecords,
  retrieveTopK,
  EMBEDDING_MODEL,
} = require("./lib/rag-core");
const { createCachedEmbedder } = require("./lib/query-cache");

const DATA_DIR = path.join(ROOT, "outputs", "human_made_data");
const EXPERIMENTS_DIR = path.join(ROOT, "outputs", "chunking_experiments");
const RESULTS_DIR = path.join(ROOT, "outputs", "eval_results");
const K = 5;

const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);

function loadQuestions() {
  const test = JSON.parse(fs.readFileSync(path.join(DATA_DIR, "test_data.json"), "utf8")).items;
  const answers = new Map(
    JSON.parse(fs.readFileSync(path.join(DATA_DIR, "answer_data.json"), "utf8")).items.map((a) => [a.id, a])
  );
  return test.map((t) => ({
    id: t.id,
    question: t.question,
    goldDocIds: answers.get(t.id).gold_document_ids || [],
  }));
}

async function main() {
  const manifest = JSON.parse(fs.readFileSync(path.join(EXPERIMENTS_DIR, "manifest.json"), "utf8"));
  const experiments = manifest.experiments.map((e) => e.experiment);
  const questions = loadQuestions();

  console.log(`사람 작성 ${questions.length}문항 × 실험 ${experiments.length}개`);

  const embed = createCachedEmbedder((text) => embedQuery(readApiKey(), text), EMBEDDING_MODEL);
  const queryEmbeddings = [];
  for (const q of questions) queryEmbeddings.push(await embed(q.question));
  const stats = embed.stats();
  console.log(`질문 임베딩: 캐시 적중 ${stats.hits} / 신규 ${stats.misses}\n`);

  const rows = [];
  for (const name of experiments) {
    let records;
    try {
      records = loadExperimentRecords(name);
    } catch (error) {
      console.log(`  ${name}: 건너뜀 (${error.message.slice(0, 60)})`);
      continue;
    }

    const scored = questions.map((q, i) => {
      const topK = retrieveTopK(queryEmbeddings[i], records, K);
      const gold = new Set(q.goldDocIds);
      const hits = topK.map((r) => gold.has(r.metadata.original_id));
      const first = hits.findIndex(Boolean);
      return {
        top1: hits[0] ? 1 : 0,
        top3: hits.slice(0, 3).some(Boolean) ? 1 : 0,
        top5: hits.some(Boolean) ? 1 : 0,
        rr: first === -1 ? 0 : 1 / (first + 1),
      };
    });

    rows.push({
      experiment: name,
      chunk_count: records.length,
      recall_at_1: mean(scored.map((s) => s.top1)),
      recall_at_3: mean(scored.map((s) => s.top3)),
      recall_at_5: mean(scored.map((s) => s.top5)),
      mrr_at_5: mean(scored.map((s) => s.rr)),
    });
    console.log(`  ${name} 완료`);
  }

  rows.sort((a, b) => b.recall_at_5 - a.recall_at_5);

  // 1차(LLM 골든셋) 순위와 나란히 비교한다.
  const llm = JSON.parse(fs.readFileSync(path.join(RESULTS_DIR, "retrieval_leaderboard.json"), "utf8"));
  const llmRank = new Map(
    [...llm].sort((a, b) => b.recall_at_5 - a.recall_at_5).map((r, i) => [r.experiment, i + 1])
  );

  console.log(`\n${"=".repeat(86)}`);
  console.log(`사람 작성 300문항 기준 순위 (괄호 = LLM 골든셋 80문항 기준 순위)`);
  console.log("=".repeat(86));
  console.log(`${"순위".padEnd(5)}${"실험".padEnd(20)}${"R@1".padStart(7)}${"R@3".padStart(8)}${"R@5".padStart(8)}${"MRR@5".padStart(8)}${"LLM셋 순위".padStart(12)}`);
  rows.forEach((r, i) => {
    const prev = llmRank.get(r.experiment);
    const move = prev ? (prev === i + 1 ? "=" : prev > i + 1 ? `▲${prev - (i + 1)}` : `▼${i + 1 - prev}`) : "신규";
    console.log(
      `${String(i + 1).padEnd(5)}${r.experiment.padEnd(20)}${r.recall_at_1.toFixed(3).padStart(7)}${r.recall_at_3.toFixed(3).padStart(8)}${r.recall_at_5.toFixed(3).padStart(8)}${r.mrr_at_5.toFixed(3).padStart(8)}${(prev ? `${prev}위 ${move}` : move).padStart(12)}`
    );
  });

  const outFile = path.join(RESULTS_DIR, "human_all_experiments.json");
  fs.writeFileSync(outFile, `${JSON.stringify({ dataset: "human_made_data", question_count: questions.length, results: rows, evaluated_at: new Date().toISOString() }, null, 2)}\n`, "utf8");
  console.log(`\n저장: ${path.relative(ROOT, outFile)}`);
}

main().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
