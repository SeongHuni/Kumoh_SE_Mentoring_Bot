const fs = require("fs");
const path = require("path");

const ROOT = process.cwd();
const OUTPUT_DIR = path.join(ROOT, "outputs", "chunking_experiments");
const MODEL = process.env.OPENAI_EMBEDDING_MODEL || "text-embedding-3-small";
const BATCH_SIZE = Number(process.env.EMBEDDING_BATCH_SIZE || 64);
const API_URL = "https://api.openai.com/v1/embeddings";

function readApiKey() {
  if (process.env.OPENAI_API_KEY) return process.env.OPENAI_API_KEY.trim();
  if (process.env["embedding-api-key"]) return process.env["embedding-api-key"].trim();

  const keyFiles = [
    path.join(ROOT, ".secrets", "embedding-api-key.txt"),
    path.join(ROOT, "embedding-api-key.txt"),
  ];

  for (const keyFile of keyFiles) {
    if (fs.existsSync(keyFile)) {
      const value = fs.readFileSync(keyFile, "utf8").trim();
      if (value) return value;
    }
  }

  throw new Error("OpenAI API key not found. Set OPENAI_API_KEY or create .secrets/embedding-api-key.txt.");
}

function readJsonl(filePath) {
  return fs
    .readFileSync(filePath, "utf8")
    .split(/\r?\n/u)
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

function appendJsonl(filePath, rows) {
  fs.appendFileSync(filePath, rows.map((row) => JSON.stringify(row)).join("\n") + "\n", "utf8");
}

function readCompletedIds(filePath) {
  if (!fs.existsSync(filePath)) return new Set();
  const ids = new Set();
  const lines = fs.readFileSync(filePath, "utf8").split(/\r?\n/u).filter(Boolean);
  for (const line of lines) {
    try {
      const row = JSON.parse(line);
      if (row.chunk_id) ids.add(row.chunk_id);
    } catch {
      // Ignore a partial last line if a previous run was interrupted.
    }
  }
  return ids;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function embedBatch(apiKey, inputs, attempt = 1) {
  const response = await fetch(API_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: MODEL,
      input: inputs,
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    const retryable = response.status === 429 || response.status >= 500;
    if (retryable && attempt < 6) {
      const delayMs = Math.min(30000, 1000 * 2 ** attempt);
      console.warn(`Retrying after ${response.status}; attempt ${attempt + 1}; delay ${delayMs}ms`);
      await sleep(delayMs);
      return embedBatch(apiKey, inputs, attempt + 1);
    }
    throw new Error(`Embedding API failed: ${response.status} ${text.slice(0, 500)}`);
  }

  const json = await response.json();
  return json.data
    .sort((a, b) => a.index - b.index)
    .map((item) => item.embedding);
}

function listExperiments(selected) {
  const entries = fs
    .readdirSync(OUTPUT_DIR, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();

  if (!selected.length) return entries;
  const wanted = new Set(selected);
  return entries.filter((name) => wanted.has(name));
}

async function embedExperiment(apiKey, experimentName) {
  const experimentDir = path.join(OUTPUT_DIR, experimentName);
  const chunksFile = path.join(experimentDir, "chunks.jsonl");
  const embeddingsFile = path.join(experimentDir, "embeddings.jsonl");
  const progressFile = path.join(experimentDir, "embedding_progress.json");

  if (!fs.existsSync(chunksFile)) {
    throw new Error(`Missing chunks file: ${chunksFile}`);
  }

  const chunks = readJsonl(chunksFile);
  const completedIds = readCompletedIds(embeddingsFile);
  const pending = chunks.filter((chunk) => !completedIds.has(chunk.metadata.chunk_id));
  const startedAt = Date.now();
  let embedded = 0;

  console.log(`${experimentName}: ${chunks.length} chunks, ${pending.length} pending`);

  for (let i = 0; i < pending.length; i += BATCH_SIZE) {
    const batch = pending.slice(i, i + BATCH_SIZE);
    const embeddings = await embedBatch(apiKey, batch.map((chunk) => chunk.page_content));
    const rows = batch.map((chunk, index) => ({
      chunk_id: chunk.metadata.chunk_id,
      original_id: chunk.metadata.original_id,
      experiment: chunk.metadata.experiment,
      model: MODEL,
      embedding: embeddings[index],
      metadata: chunk.metadata,
    }));

    appendJsonl(embeddingsFile, rows);
    embedded += rows.length;

    const progress = {
      experiment: experimentName,
      model: MODEL,
      total_chunks: chunks.length,
      previously_completed: completedIds.size,
      newly_embedded: embedded,
      completed_chunks: completedIds.size + embedded,
      pending_chunks: pending.length - embedded,
      batch_size: BATCH_SIZE,
      updated_at: new Date().toISOString(),
      elapsed_seconds: Math.round((Date.now() - startedAt) / 1000),
    };
    fs.writeFileSync(progressFile, JSON.stringify(progress, null, 2) + "\n", "utf8");

    console.log(`${experimentName}: ${progress.completed_chunks}/${chunks.length}`);
  }
}

async function main() {
  const apiKey = readApiKey();
  const selected = process.argv.slice(2);
  const experiments = listExperiments(selected);
  if (!experiments.length) {
    throw new Error("No chunking experiment directories found.");
  }

  console.log(`Embedding model: ${MODEL}`);
  console.log(`Batch size: ${BATCH_SIZE}`);
  console.log(`Experiments: ${experiments.join(", ")}`);

  for (const experimentName of experiments) {
    await embedExperiment(apiKey, experimentName);
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
