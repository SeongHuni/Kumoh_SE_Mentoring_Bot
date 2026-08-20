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
  buildPrompt,
  generateAnswer,
  chatJson,
} = require("./lib/rag-core");

const GOLDEN_FILE = path.join(ROOT, "outputs", "golden_set", "golden_questions.jsonl");
const RESULTS_DIR = path.join(ROOT, "outputs", "eval_results");
const RAW_FILE = path.join(RESULTS_DIR, "generation_raw.jsonl");
const LEADERBOARD_FILE = path.join(RESULTS_DIR, "generation_leaderboard.json");
const K = 5;
// Fixed across every experiment on purpose — chunking is the only variable under test.
const CHAT_MODEL = process.env.OPENAI_CHAT_MODEL || "gpt-4o-mini";
const CONCURRENCY = Number(process.env.EVAL_CONCURRENCY || 5);

const DIMENSIONS = ["정확도", "근거충실도", "세부정보보존", "출처제시", "완성도"];

const JUDGE_SYSTEM =
  "당신은 대학 학과 챗봇 답변을 평가하는 채점자입니다. 아래 5개 항목을 각각 0, 1, 2점으로 채점하세요.\n" +
  "점수 기준: 2=정확하고 근거가 충분함, 1=대체로 맞지만 일부 정보가 부족하거나 애매함, 0=틀렸거나 근거가 없음.\n\n" +
  "평가 항목:\n" +
  "1. 정확도: 질문에 맞는 답을 했는가\n" +
  "2. 근거충실도: 검색된 참고 자료 내용만으로 답했는가 (참고 자료에 없는 내용을 지어내지 않았는가)\n" +
  "3. 세부정보보존: 날짜, 신청 기간, 장소, 대상, 교수명, 과목명, 문의처 등 세부사항이 정확한가\n" +
  "4. 출처제시: 참고 자료의 제목/출처를 답변에서 언급했는가\n" +
  "5. 완성도: 사용자가 바로 이해하고 행동할 수 있는가\n\n" +
  '다음 JSON으로만 응답하세요: {"정확도": 0|1|2, "근거충실도": 0|1|2, "세부정보보존": 0|1|2, ' +
  '"출처제시": 0|1|2, "완성도": 0|1|2, "판정_근거": "간단한 이유"}';

function buildJudgePrompt(question, referenceAnswer, checkpoints, retrieved, answer) {
  const context = retrieved.map((r, i) => `[${i + 1}] ${r.page_content}`).join("\n\n");
  const user =
    `질문: ${question}\n참고 답변(정답 기준): ${referenceAnswer}\n` +
    `확인해야 할 항목: ${JSON.stringify(checkpoints)}\n\n챗봇이 실제로 검색한 참고 자료:\n${context}\n\n` +
    `챗봇의 실제 답변:\n${answer}`;
  return { system: JUDGE_SYSTEM, user };
}

async function mapWithConcurrency(items, limit, fn) {
  const results = new Array(items.length);
  let index = 0;

  async function worker() {
    while (index < items.length) {
      const current = index;
      index += 1;
      results[current] = await fn(items[current], current);
    }
  }

  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, () => worker()));
  return results;
}

function loadCompletedKeys() {
  if (!fs.existsSync(RAW_FILE)) return new Set();
  return new Set(readJsonl(RAW_FILE).map((r) => `${r.experiment}::${r.question}`));
}

function buildLeaderboard(rows) {
  const byExperiment = {};
  for (const row of rows) {
    if (!byExperiment[row.experiment]) byExperiment[row.experiment] = [];
    byExperiment[row.experiment].push(row);
  }

  const leaderboard = Object.entries(byExperiment).map(([experiment, expRows]) => {
    const dimMeans = {};
    for (const dim of DIMENSIONS) {
      dimMeans[dim] = expRows.reduce((sum, r) => sum + (r.judge?.[dim] ?? 0), 0) / expRows.length;
    }
    const composite = DIMENSIONS.reduce((sum, dim) => sum + dimMeans[dim], 0) / DIMENSIONS.length;
    return { experiment, question_count: expRows.length, ...dimMeans, composite_avg_of_avgs: composite };
  });

  leaderboard.sort((a, b) => b.composite_avg_of_avgs - a.composite_avg_of_avgs);
  return leaderboard;
}

async function main() {
  const manifest = JSON.parse(fs.readFileSync(path.join(EXPERIMENTS_DIR, "manifest.json"), "utf8"));
  const experiments = manifest.experiments.map((e) => e.experiment);
  const questions = readJsonl(GOLDEN_FILE);
  const apiKey = readApiKey();

  fs.mkdirSync(RESULTS_DIR, { recursive: true });

  console.log(`Embedding ${questions.length} golden questions...`);
  const queryEmbeddings = [];
  for (const q of questions) queryEmbeddings.push(await embedQuery(apiKey, q.question));

  const completed = loadCompletedKeys();
  const tasks = [];
  experiments.forEach((experimentName) => {
    questions.forEach((q, qi) => {
      const key = `${experimentName}::${q.question}`;
      if (!completed.has(key)) tasks.push({ experimentName, question: q, queryEmbedding: queryEmbeddings[qi] });
    });
  });

  console.log(
    `Generation eval: ${tasks.length} pending / ${experiments.length * questions.length} total ` +
      `(${experiments.length} experiments x ${questions.length} questions), concurrency=${CONCURRENCY}`
  );

  const recordsCache = new Map();
  function getRecords(experimentName) {
    if (!recordsCache.has(experimentName)) recordsCache.set(experimentName, loadExperimentRecords(experimentName));
    return recordsCache.get(experimentName);
  }

  let done = 0;
  await mapWithConcurrency(tasks, CONCURRENCY, async (task) => {
    const records = getRecords(task.experimentName);
    const retrieved = retrieveTopK(task.queryEmbedding, records, K);
    const prompt = buildPrompt(task.question.question, retrieved);
    const answer = await generateAnswer(apiKey, CHAT_MODEL, prompt, 0);
    const judgePrompt = buildJudgePrompt(
      task.question.question,
      task.question.reference_answer,
      task.question.answer_checkpoints,
      retrieved,
      answer
    );
    const judge = await chatJson(apiKey, CHAT_MODEL, judgePrompt, 0);

    const row = {
      experiment: task.experimentName,
      question: task.question.question,
      gold_category: task.question.gold_category,
      retrieved_chunk_ids: retrieved.map((r) => r.chunk_id),
      answer,
      judge,
    };
    fs.appendFileSync(RAW_FILE, `${JSON.stringify(row)}\n`, "utf8");
    done += 1;
    if (done % 20 === 0 || done === tasks.length) console.log(`  ${done}/${tasks.length}`);
  });

  const leaderboard = buildLeaderboard(readJsonl(RAW_FILE));
  fs.writeFileSync(LEADERBOARD_FILE, `${JSON.stringify(leaderboard, null, 2)}\n`, "utf8");

  console.log("\n=== Generation Leaderboard (sorted by composite avg-of-avgs, 0-2 scale) ===");
  console.log(
    leaderboard
      .map(
        (row) =>
          `${row.experiment.padEnd(20)} 정확도=${row.정확도.toFixed(2)} 근거충실도=${row.근거충실도.toFixed(
            2
          )} 세부정보보존=${row.세부정보보존.toFixed(2)} 출처제시=${row.출처제시.toFixed(2)} ` +
          `완성도=${row.완성도.toFixed(2)} composite=${row.composite_avg_of_avgs.toFixed(2)}`
      )
      .join("\n")
  );

  console.log(`\nSaved: ${path.relative(ROOT, LEADERBOARD_FILE)}`);
  console.log(`Saved: ${path.relative(ROOT, RAW_FILE)}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
