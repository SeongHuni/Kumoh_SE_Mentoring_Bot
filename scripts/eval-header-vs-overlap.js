// 헤더 주입 방식 vs overlap 방식 비교 (2x2 통제 실험).
//   node scripts/eval-header-vs-overlap.js
//
//                  overlap 0        overlap 50
//   헤더 있음      D_500            K_500_ov50
//   헤더 없음      N_500_nohdr      O_500_nohdr_ov50
//
// 네 칸 모두 분할 로직(splitWithOverlap)과 청크 크기(500 tokens)가 동일하고
// 조작 변인은 '헤더 유무'와 'overlap 유무' 둘뿐이다.
//
// 평가셋: outputs/human_made_data (사람이 작성한 300문항)
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
const RESULTS_DIR = path.join(ROOT, "outputs", "eval_results");
const K = 5;

const CELLS = [
  { experiment: "D_500", header: true, overlap: 0 },
  { experiment: "K_500_ov50", header: true, overlap: 50 },
  { experiment: "N_500_nohdr", header: false, overlap: 0 },
  { experiment: "O_500_nohdr_ov50", header: false, overlap: 50 },
];

const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);

function loadQuestions() {
  const test = JSON.parse(fs.readFileSync(path.join(DATA_DIR, "test_data.json"), "utf8")).items;
  const answers = JSON.parse(fs.readFileSync(path.join(DATA_DIR, "answer_data.json"), "utf8")).items;
  const byId = new Map(answers.map((a) => [a.id, a]));

  return test.map((t) => {
    const a = byId.get(t.id);
    if (!a) throw new Error(`answer_data.json에 id가 없습니다: ${t.id}`);
    return {
      id: t.id,
      question: t.question,
      category: t.source_category,
      source: t.source_type,
      goldDocIds: a.gold_document_ids || [],
      expectedEvidence: a.expected_evidence || [],
    };
  });
}

function scoreQuestion(queryEmbedding, records, goldDocIds) {
  const topK = retrieveTopK(queryEmbedding, records, K);
  const gold = new Set(goldDocIds);
  const hits = topK.map((r) => gold.has(r.metadata.original_id));
  const first = hits.findIndex(Boolean);

  return {
    top1: hits[0] ? 1 : 0,
    top3: hits.slice(0, 3).some(Boolean) ? 1 : 0,
    top5: hits.some(Boolean) ? 1 : 0,
    rr: first === -1 ? 0 : 1 / (first + 1),
    ctxP: hits.filter(Boolean).length / K,
    retrieved: topK.map((r) => ({
      chunk_id: r.chunk_id,
      original_id: r.metadata.original_id,
      score: r.score,
    })),
  };
}

async function main() {
  const questions = loadQuestions();
  const apiKey = readApiKey();

  console.log(`평가셋: 사람 작성 ${questions.length}문항`);
  console.log(`질문 임베딩 준비 중... (4개 실험이 동일 임베딩을 공유, 디스크 캐시 사용)`);

  // 크레딧 소진 등으로 중단돼도 이미 만든 임베딩은 재사용한다.
  const embed = createCachedEmbedder((text) => embedQuery(apiKey, text), EMBEDDING_MODEL);

  const queryEmbeddings = [];
  for (let i = 0; i < questions.length; i += 1) {
    queryEmbeddings.push(await embed(questions[i].question));
    if ((i + 1) % 50 === 0) console.log(`  ${i + 1}/${questions.length}`);
  }
  const stats = embed.stats();
  console.log(`  캐시 적중 ${stats.hits} / 신규 생성 ${stats.misses}`);

  fs.mkdirSync(RESULTS_DIR, { recursive: true });
  const rawFile = path.join(RESULTS_DIR, "header_vs_overlap_raw.jsonl");
  fs.writeFileSync(rawFile, "", "utf8");

  const results = [];

  for (const cell of CELLS) {
    console.log(`평가 중: ${cell.experiment}...`);
    const records = loadExperimentRecords(cell.experiment);

    const scored = questions.map((q, i) => {
      const s = scoreQuestion(queryEmbeddings[i], records, q.goldDocIds);
      fs.appendFileSync(
        rawFile,
        `${JSON.stringify({ experiment: cell.experiment, id: q.id, question: q.question, category: q.category, source: q.source, gold_document_ids: q.goldDocIds, ...s })}\n`,
        "utf8"
      );
      return s;
    });

    results.push({
      ...cell,
      chunk_count: records.length,
      recall_at_1: mean(scored.map((s) => s.top1)),
      recall_at_3: mean(scored.map((s) => s.top3)),
      recall_at_5: mean(scored.map((s) => s.top5)),
      mrr_at_5: mean(scored.map((s) => s.rr)),
      context_precision_at_5: mean(scored.map((s) => s.ctxP)),
      question_count: questions.length,
    });
  }

  const get = (header, overlap) => results.find((r) => r.header === header && r.overlap === overlap);
  const fmt = (n) => n.toFixed(3).padStart(6);
  const delta = (a, b) => `${b - a >= 0 ? "+" : ""}${(b - a).toFixed(3)}`;

  console.log(`\n${"=".repeat(78)}`);
  console.log(`헤더 vs overlap 2x2 (사람 작성 ${questions.length}문항)`);
  console.log("=".repeat(78));
  console.log(`${"".padEnd(22)}${"R@1".padStart(6)}${"R@3".padStart(8)}${"R@5".padStart(8)}${"MRR@5".padStart(8)}${"ctxP@5".padStart(8)}`);
  for (const r of results) {
    const label = `${r.header ? "헤더O" : "헤더X"} / ov${r.overlap}`;
    console.log(
      `${label.padEnd(22)}${fmt(r.recall_at_1)}${fmt(r.recall_at_3).padStart(8)}${fmt(r.recall_at_5).padStart(8)}${fmt(r.mrr_at_5).padStart(8)}${fmt(r.context_precision_at_5).padStart(8)}`
    );
  }

  console.log(`\n--- 주효과 ---`);
  const h0 = get(true, 0);
  const h50 = get(true, 50);
  const n0 = get(false, 0);
  const n50 = get(false, 50);

  console.log(`헤더 효과 (overlap 0에서):   R@3 ${delta(n0.recall_at_3, h0.recall_at_3)}  MRR ${delta(n0.mrr_at_5, h0.mrr_at_5)}`);
  console.log(`헤더 효과 (overlap 50에서):  R@3 ${delta(n50.recall_at_3, h50.recall_at_3)}  MRR ${delta(n50.mrr_at_5, h50.mrr_at_5)}`);
  console.log(`overlap 효과 (헤더 있음):    R@3 ${delta(h0.recall_at_3, h50.recall_at_3)}  MRR ${delta(h0.mrr_at_5, h50.mrr_at_5)}`);
  console.log(`overlap 효과 (헤더 없음):    R@3 ${delta(n0.recall_at_3, n50.recall_at_3)}  MRR ${delta(n0.mrr_at_5, n50.mrr_at_5)}`);

  // 300문항 기준 1문항 = 0.33pp. 노이즈 판단 기준을 같이 출력한다.
  console.log(`\n1문항 = ${(100 / questions.length).toFixed(2)}pp`);

  const summaryFile = path.join(RESULTS_DIR, "header_vs_overlap.json");
  fs.writeFileSync(summaryFile, `${JSON.stringify({ dataset: "human_made_data", question_count: questions.length, results, evaluated_at: new Date().toISOString() }, null, 2)}\n`, "utf8");
  console.log(`\n저장: ${path.relative(ROOT, summaryFile)}`);
  console.log(`저장: ${path.relative(ROOT, rawFile)}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
