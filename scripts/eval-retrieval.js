const fs = require("fs");
const path = require("path");
const {
  ROOT,
  EXPERIMENTS_DIR,
  readApiKey,
  readJsonl,
  embedQuery,
  loadExperimentRecords,
  retrieveTopK,
} = require("./lib/rag-core");

const GOLDEN_FILE = path.join(ROOT, "outputs", "golden_set", "golden_questions.jsonl");
const RESULTS_DIR = path.join(ROOT, "outputs", "eval_results");
const K = 5;

function percentile(values, p) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor((sorted.length - 1) * p)];
}

function mean(values) {
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0;
}

function evaluateQuestion(queryEmbedding, records, goldIds, k) {
  const start = process.hrtime.bigint();
  const topK = retrieveTopK(queryEmbedding, records, k);
  const latencyMs = Number(process.hrtime.bigint() - start) / 1e6;

  const goldSet = new Set(goldIds);
  const hitFlags = topK.map((r) => goldSet.has(r.metadata.original_id));

  const top3Hit = hitFlags.slice(0, 3).some(Boolean) ? 1 : 0;
  const top5Hit = hitFlags.some(Boolean) ? 1 : 0;
  const firstHitRank = hitFlags.findIndex(Boolean);
  const rr5 = firstHitRank === -1 ? 0 : 1 / (firstHitRank + 1);
  const contextPrecision5 = hitFlags.filter(Boolean).length / k;

  return {
    latencyMs,
    top3Hit,
    top5Hit,
    rr5,
    contextPrecision5,
    retrieved: topK.map((r) => ({
      chunk_id: r.chunk_id,
      original_id: r.metadata.original_id,
      score: r.score,
    })),
  };
}

async function main() {
  const manifest = JSON.parse(fs.readFileSync(path.join(EXPERIMENTS_DIR, "manifest.json"), "utf8"));
  const experiments = manifest.experiments.map((e) => e.experiment);
  const questions = readJsonl(GOLDEN_FILE);

  console.log(`Embedding ${questions.length} golden questions (shared across ${experiments.length} experiments)...`);
  const apiKey = readApiKey();
  const queryEmbeddings = [];
  for (const q of questions) {
    queryEmbeddings.push(await embedQuery(apiKey, q.question));
  }

  fs.mkdirSync(RESULTS_DIR, { recursive: true });
  const rawFile = path.join(RESULTS_DIR, "retrieval_raw.jsonl");
  fs.writeFileSync(rawFile, "", "utf8");

  const leaderboard = [];

  for (const experimentName of experiments) {
    console.log(`Evaluating ${experimentName}...`);
    const records = loadExperimentRecords(experimentName);

    const perQuestion = questions.map((q, i) => {
      const result = evaluateQuestion(queryEmbeddings[i], records, q.gold_doc_ids, K);
      fs.appendFileSync(
        rawFile,
        `${JSON.stringify({
          experiment: experimentName,
          question: q.question,
          gold_doc_ids: q.gold_doc_ids,
          gold_category: q.gold_category,
          ...result,
        })}\n`,
        "utf8"
      );
      return result;
    });

    const latencies = perQuestion.map((r) => r.latencyMs);
    leaderboard.push({
      experiment: experimentName,
      chunk_count: records.length,
      recall_at_3: mean(perQuestion.map((r) => r.top3Hit)),
      recall_at_5: mean(perQuestion.map((r) => r.top5Hit)),
      mrr_at_5: mean(perQuestion.map((r) => r.rr5)),
      context_precision_at_5: mean(perQuestion.map((r) => r.contextPrecision5)),
      mean_latency_ms: mean(latencies),
      p90_latency_ms: percentile(latencies, 0.9),
      question_count: questions.length,
    });
  }

  leaderboard.sort((a, b) => b.recall_at_5 - a.recall_at_5);

  const leaderboardFile = path.join(RESULTS_DIR, "retrieval_leaderboard.json");
  fs.writeFileSync(leaderboardFile, `${JSON.stringify(leaderboard, null, 2)}\n`, "utf8");

  console.log("\n=== Retrieval Leaderboard (sorted by Recall@5) ===");
  console.log(
    leaderboard
      .map(
        (row) =>
          `${row.experiment.padEnd(20)} recall@3=${row.recall_at_3.toFixed(3)} recall@5=${row.recall_at_5.toFixed(
            3
          )} mrr@5=${row.mrr_at_5.toFixed(3)} ctxP@5=${row.context_precision_at_5.toFixed(
            3
          )} chunks=${row.chunk_count} latency(ms)=${row.mean_latency_ms.toFixed(2)}`
      )
      .join("\n")
  );

  console.log(`\nSaved: ${path.relative(ROOT, leaderboardFile)}`);
  console.log(`Saved: ${path.relative(ROOT, rawFile)}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
