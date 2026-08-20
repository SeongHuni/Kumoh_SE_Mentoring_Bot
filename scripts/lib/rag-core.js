const fs = require("fs");
const path = require("path");

const ROOT = process.cwd();
const EXPERIMENTS_DIR = path.join(ROOT, "outputs", "chunking_experiments");
const EMBEDDING_MODEL = process.env.OPENAI_EMBEDDING_MODEL || "text-embedding-3-small";
const EMBEDDING_API_URL = "https://api.openai.com/v1/embeddings";
const CHAT_API_URL = "https://api.openai.com/v1/chat/completions";

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

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchWithRetry(url, options, attempt = 1, maxAttempts = 6) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    const retryable = response.status === 429 || response.status >= 500;
    if (retryable && attempt < maxAttempts) {
      const delayMs = Math.min(30000, 1000 * 2 ** attempt);
      await sleep(delayMs);
      return fetchWithRetry(url, options, attempt + 1, maxAttempts);
    }
    throw new Error(`API request failed: ${response.status} ${text.slice(0, 500)}`);
  }
  return response;
}

async function embedQuery(apiKey, question, model = EMBEDDING_MODEL) {
  const response = await fetchWithRetry(EMBEDDING_API_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ model, input: question }),
  });

  const json = await response.json();
  return json.data[0].embedding;
}

async function embedBatch(apiKey, inputs, model = EMBEDDING_MODEL) {
  const response = await fetchWithRetry(EMBEDDING_API_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ model, input: inputs }),
  });

  const json = await response.json();
  return json.data.sort((a, b) => a.index - b.index).map((item) => item.embedding);
}

function cosineSimilarity(a, b) {
  let dot = 0;
  let normA = 0;
  let normB = 0;
  for (let i = 0; i < a.length; i += 1) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  return dot / (Math.sqrt(normA) * Math.sqrt(normB));
}

function loadExperimentRecords(experimentName, experimentsDir = EXPERIMENTS_DIR) {
  const dir = path.join(experimentsDir, experimentName);
  const chunks = readJsonl(path.join(dir, "chunks.jsonl"));
  const embeddings = readJsonl(path.join(dir, "embeddings.jsonl"));

  const contentByChunkId = new Map(chunks.map((chunk) => [chunk.metadata.chunk_id, chunk.page_content]));

  return embeddings.map((row) => ({
    chunk_id: row.chunk_id,
    metadata: row.metadata,
    embedding: row.embedding,
    page_content: contentByChunkId.get(row.chunk_id) || "",
  }));
}

function retrieveTopK(queryEmbedding, records, k) {
  return records
    .map((record) => ({ ...record, score: cosineSimilarity(queryEmbedding, record.embedding) }))
    .sort((a, b) => b.score - a.score)
    .slice(0, k);
}

function buildPrompt(question, retrieved) {
  const context = retrieved
    .map((r, i) => {
      const meta = r.metadata || {};
      const header = [meta.title, meta.source, meta.category].filter(Boolean).join(" | ");
      return `[${i + 1}] (${header})\n${r.page_content}`;
    })
    .join("\n\n---\n\n");

  return {
    system:
      "당신은 대학 학과 챗봇입니다. 아래 제공된 참고 자료만 근거로 답변하세요. " +
      "자료에 근거가 없으면 모른다고 답하세요. 답변 마지막 줄에 참고한 자료 번호를 [1], [2]처럼 표시하세요.",
    user: `질문: ${question}\n\n참고 자료:\n${context}`,
  };
}

async function generateAnswer(apiKey, model, prompt, temperature = 0) {
  const response = await fetchWithRetry(CHAT_API_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      temperature,
      messages: [
        { role: "system", content: prompt.system },
        { role: "user", content: prompt.user },
      ],
    }),
  });

  const json = await response.json();
  return json.choices[0].message.content.trim();
}

async function chatJson(apiKey, model, { system, user }, temperature = 0) {
  const response = await fetchWithRetry(CHAT_API_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      temperature,
      response_format: { type: "json_object" },
      messages: [
        { role: "system", content: system },
        { role: "user", content: user },
      ],
    }),
  });

  const json = await response.json();
  return JSON.parse(json.choices[0].message.content);
}

module.exports = {
  ROOT,
  EXPERIMENTS_DIR,
  EMBEDDING_MODEL,
  readApiKey,
  readJsonl,
  sleep,
  fetchWithRetry,
  embedQuery,
  embedBatch,
  cosineSimilarity,
  loadExperimentRecords,
  retrieveTopK,
  buildPrompt,
  generateAnswer,
  chatJson,
};
