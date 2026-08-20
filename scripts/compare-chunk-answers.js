const fs = require("fs");
const path = require("path");
const {
  ROOT,
  EXPERIMENTS_DIR,
  EMBEDDING_MODEL,
  readApiKey,
  embedQuery,
  loadExperimentRecords,
  retrieveTopK,
  buildPrompt,
  generateAnswer,
} = require("./lib/rag-core");

const RESULTS_DIR = path.join(ROOT, "outputs", "answer_comparisons");
const CHAT_MODEL = process.env.OPENAI_CHAT_MODEL || "gpt-4o-mini";
const DEFAULT_TOP_K = Number(process.env.TOP_K || 5);

function parseArgs(argv) {
  const args = { question: null, experiments: null, k: DEFAULT_TOP_K, model: CHAT_MODEL };
  const rest = [];

  for (const token of argv) {
    if (token.startsWith("--experiments=")) {
      args.experiments = token
        .slice("--experiments=".length)
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
    } else if (token.startsWith("--k=")) {
      args.k = Number(token.slice("--k=".length));
    } else if (token.startsWith("--model=")) {
      args.model = token.slice("--model=".length);
    } else {
      rest.push(token);
    }
  }

  args.question = rest.join(" ").trim();
  return args;
}

function listExperiments(selected) {
  const manifest = JSON.parse(fs.readFileSync(path.join(EXPERIMENTS_DIR, "manifest.json"), "utf8"));
  const names = manifest.experiments.map((entry) => entry.experiment);
  if (!selected || !selected.length) return names;
  const wanted = new Set(selected);
  return names.filter((name) => wanted.has(name));
}

function slugify(text) {
  const slug = text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
  return slug || "question";
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.question) {
    throw new Error(
      'Usage: node scripts/compare-chunk-answers.js "질문" [--experiments=B_150,D_500] [--k=5] [--model=gpt-4o-mini]'
    );
  }

  const apiKey = readApiKey();
  const experimentNames = listExperiments(args.experiments);
  if (!experimentNames.length) throw new Error("No matching experiments found.");

  console.log(`질문: ${args.question}`);
  console.log(`검색 top-k: ${args.k}, 답변 모델: ${args.model}`);
  console.log(`비교 실험: ${experimentNames.join(", ")}`);

  const queryEmbedding = await embedQuery(apiKey, args.question);
  const results = [];

  for (const experimentName of experimentNames) {
    console.log(`\n=== ${experimentName} ===`);
    const records = loadExperimentRecords(experimentName);
    const retrieved = retrieveTopK(queryEmbedding, records, args.k);
    const prompt = buildPrompt(args.question, retrieved);
    const answer = await generateAnswer(apiKey, args.model, prompt);

    console.log("검색된 청크:");
    retrieved.forEach((r, i) => {
      const preview = r.page_content.replace(/\s+/g, " ").slice(0, 80);
      console.log(`  [${i + 1}] score=${r.score.toFixed(4)} id=${r.chunk_id}`);
      console.log(`      ${preview}...`);
    });

    console.log("\n답변:");
    console.log(answer);

    results.push({
      experiment: experimentName,
      retrieved: retrieved.map((r) => ({
        chunk_id: r.chunk_id,
        score: r.score,
        metadata: r.metadata,
        page_content: r.page_content,
      })),
      answer,
    });
  }

  fs.mkdirSync(RESULTS_DIR, { recursive: true });
  const outFile = path.join(RESULTS_DIR, `${slugify(args.question)}.json`);
  fs.writeFileSync(
    outFile,
    JSON.stringify(
      {
        question: args.question,
        k: args.k,
        chat_model: args.model,
        embedding_model: EMBEDDING_MODEL,
        results,
        created_at: new Date().toISOString(),
      },
      null,
      2
    ) + "\n",
    "utf8"
  );

  console.log(`\n결과 저장: ${path.relative(ROOT, outFile)}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
