const fs = require("fs");
const path = require("path");
const {
  ensureDir,
  jsonlStringify,
  percentile,
  countBy,
  estimateTokenCount,
  stripExistingHeader,
  buildHeader,
  splitSentences,
  recursiveSegments,
  packLeavesToChunks,
  mergeManifest,
} = require("./lib/chunking-common");
const { readApiKey, embedBatch, cosineSimilarity, EMBEDDING_MODEL } = require("./lib/rag-core");

const ROOT = process.cwd();
const INPUT_FILE = path.join(ROOT, "data", "document통합파일(에타리뷰분리).json");
const OUTPUT_DIR = path.join(ROOT, "outputs", "chunking_experiments");
const EXPERIMENT = { name: "J_semantic", label: "J", meaning: "Semantic Chunking (인접 유사도 기반 경계 + 강제 병합 오버라이드)" };

const EXPERIMENT_DIR = path.join(OUTPUT_DIR, EXPERIMENT.name);
const SENTENCE_EMBEDDINGS_FILE = path.join(EXPERIMENT_DIR, "sentence_embeddings.jsonl");
const BATCH_SIZE = Number(process.env.EMBEDDING_BATCH_SIZE || 64);

const MIN_TOKENS = 120;
const TARGET_TOKENS = 500;
const MAX_TOKENS = 900;

// Keyword groups that must never be split apart, per the plan doc's Phase 5 spec.
const MERGE_GROUPS = [
  ["신청기간", "접수기간", "신청 기간", "접수 기간", "신청방법", "신청 방법"],
  ["지원대상", "신청대상", "지원 대상", "신청 대상", "제외대상", "제외 대상"],
  ["제출서류", "제출 서류", "제출처", "제출 처"],
  ["일정", "장소"],
  ["과목명", "과목", "교수명", "교수", "강의평"],
  ["문의처", "문의 처", "담당부서", "담당 부서", "담당자"],
];

function readJsonlIfExists(filePath) {
  if (!fs.existsSync(filePath)) return [];
  return fs
    .readFileSync(filePath, "utf8")
    .split(/\r?\n/u)
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

function appendJsonl(filePath, rows) {
  fs.appendFileSync(filePath, rows.map((row) => JSON.stringify(row)).join("\n") + "\n", "utf8");
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Embeds every sentence/short-paragraph unit across the whole corpus, batched with
// resumable progress (skips units already present in sentence_embeddings.jsonl) — same
// pattern as embed-chunks.js, since this can be a few hundred batched API calls.
async function embedAllUnits(apiKey, flatUnits) {
  const completed = new Set(readJsonlIfExists(SENTENCE_EMBEDDINGS_FILE).map((row) => row.key));
  const pending = flatUnits.filter((u) => !completed.has(u.key));

  console.log(`Semantic chunking: ${flatUnits.length} sentence units, ${pending.length} pending embedding`);

  for (let i = 0; i < pending.length; i += BATCH_SIZE) {
    const batch = pending.slice(i, i + BATCH_SIZE);
    const embeddings = await embedBatch(apiKey, batch.map((u) => u.text), EMBEDDING_MODEL);
    const rows = batch.map((u, idx) => ({ key: u.key, embedding: embeddings[idx] }));
    appendJsonl(SENTENCE_EMBEDDINGS_FILE, rows);
    console.log(`  embedded ${Math.min(i + BATCH_SIZE, pending.length)}/${pending.length}`);
  }

  const all = readJsonlIfExists(SENTENCE_EMBEDDINGS_FILE);
  return new Map(all.map((row) => [row.key, row.embedding]));
}

function meanStd(values) {
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const variance = values.reduce((a, b) => a + (b - mean) ** 2, 0) / values.length;
  return { mean, std: Math.sqrt(variance) };
}

function detectBreakpoints(sims) {
  const breakpoints = new Set();
  if (!sims.length) return breakpoints;
  const { mean, std } = meanStd(sims);
  const threshold = mean - std;
  sims.forEach((sim, i) => {
    if (sim < threshold) breakpoints.add(i); // boundary between unit i and unit i+1
  });
  return breakpoints;
}

function groupsOf(text) {
  const idxs = [];
  MERGE_GROUPS.forEach((group, gi) => {
    if (group.some((kw) => text.includes(kw))) idxs.push(gi);
  });
  return idxs;
}

function shouldForceMerge(unitA, unitB) {
  const groupsA = groupsOf(unitA);
  if (!groupsA.length) return false;
  const groupsB = groupsOf(unitB);
  return groupsA.some((g) => groupsB.includes(g));
}

function buildSegments(units, breakpoints) {
  const segments = [];
  let current = [];
  units.forEach((unit, i) => {
    current.push(unit);
    if (breakpoints.has(i)) {
      segments.push(current.join(" "));
      current = [];
    }
  });
  if (current.length) segments.push(current.join(" "));
  return segments;
}

// Merges runs of undersized segments forward; any leftover tiny remainder at the end
// merges into the previous segment instead of surviving as its own tiny chunk.
function mergeTinySegments(segments, minTokens) {
  const result = [];
  let bucket = "";
  for (const seg of segments) {
    bucket = bucket ? `${bucket}\n${seg}` : seg;
    if (estimateTokenCount(bucket) >= minTokens) {
      result.push(bucket);
      bucket = "";
    }
  }
  if (bucket) {
    if (result.length) {
      result[result.length - 1] = `${result[result.length - 1]}\n${bucket}`;
    } else {
      result.push(bucket);
    }
  }
  return result;
}

function resplitOversized(segments, maxTokens, targetTokens) {
  const result = [];
  for (const seg of segments) {
    if (estimateTokenCount(seg) <= maxTokens) {
      result.push(seg);
      continue;
    }
    const leaves = recursiveSegments(seg, targetTokens);
    result.push(...packLeavesToChunks(leaves, targetTokens));
  }
  return result;
}

function semanticSegmentsForDoc(units, embeddings) {
  if (units.length <= 1) return units.length ? [units[0]] : [];

  const sims = [];
  for (let i = 0; i < units.length - 1; i += 1) {
    sims.push(cosineSimilarity(embeddings[i], embeddings[i + 1]));
  }

  const breakpoints = detectBreakpoints(sims);
  for (const i of Array.from(breakpoints)) {
    if (shouldForceMerge(units[i], units[i + 1])) breakpoints.delete(i);
  }

  let segments = buildSegments(units, breakpoints);
  segments = mergeTinySegments(segments, MIN_TOKENS);
  segments = resplitOversized(segments, MAX_TOKENS, TARGET_TOKENS);
  return segments;
}

function buildStats(docs, chunks) {
  const tokenCounts = chunks.map((chunk) => chunk.metadata.estimated_tokens);
  const chunksPerDoc = Object.values(countBy(chunks, (chunk) => chunk.metadata.original_id));

  return {
    experiment: EXPERIMENT.name,
    experiment_label: EXPERIMENT.label,
    meaning: EXPERIMENT.meaning,
    splitting_method: "semantic",
    source_file: path.basename(INPUT_FILE),
    document_count: docs.length,
    chunk_count: chunks.length,
    chunk_size_tokens: null,
    chunk_overlap_tokens: 0,
    token_count_method: "estimated_local_no_tiktoken",
    estimated_tokens: {
      total: tokenCounts.reduce((sum, value) => sum + value, 0),
      min: Math.min(...tokenCounts),
      median: percentile(tokenCounts, 0.5),
      p75: percentile(tokenCounts, 0.75),
      p90: percentile(tokenCounts, 0.9),
      p95: percentile(tokenCounts, 0.95),
      max: Math.max(...tokenCounts),
    },
    chunks_per_document: {
      min: Math.min(...chunksPerDoc),
      median: percentile(chunksPerDoc, 0.5),
      p75: percentile(chunksPerDoc, 0.75),
      p90: percentile(chunksPerDoc, 0.9),
      max: Math.max(...chunksPerDoc),
    },
    source_counts: countBy(chunks, (chunk) => chunk.metadata.source),
    category_counts: countBy(chunks, (chunk) => chunk.metadata.category),
    created_at: new Date().toISOString(),
  };
}

async function main() {
  ensureDir(OUTPUT_DIR);
  ensureDir(EXPERIMENT_DIR);

  const docs = JSON.parse(fs.readFileSync(INPUT_FILE, "utf8"));
  if (!Array.isArray(docs)) {
    throw new Error("Input file must contain a JSON array.");
  }

  const perDocUnits = docs.map((doc) => splitSentences(stripExistingHeader(doc.page_content)));

  const flatUnits = [];
  perDocUnits.forEach((units, docIndex) => {
    if (units.length <= 1) return; // nothing to compare, no embedding needed
    units.forEach((text, unitIndex) => {
      flatUnits.push({ key: `${docIndex}:${unitIndex}`, docIndex, unitIndex, text });
    });
  });

  const apiKey = readApiKey();
  const embeddingByKey = await embedAllUnits(apiKey, flatUnits);

  const rows = [];
  docs.forEach((doc, docIndex) => {
    const metadata = doc.metadata || {};
    const originalId = metadata.id || `doc-${docIndex}`;
    const header = buildHeader(metadata);
    const units = perDocUnits[docIndex];
    const embeddings = units.map((_, unitIndex) => embeddingByKey.get(`${docIndex}:${unitIndex}`));

    const bodyChunks = semanticSegmentsForDoc(units, embeddings);

    bodyChunks.forEach((bodyChunk, index) => {
      const content = header ? `${header}\n\n${bodyChunk}`.trim() : bodyChunk.trim();
      rows.push({
        page_content: content,
        metadata: {
          ...metadata,
          original_id: originalId,
          chunk_id: `${originalId}::${EXPERIMENT.name}::${String(index).padStart(4, "0")}`,
          chunk_index: index,
          chunk_count: bodyChunks.length,
          experiment: EXPERIMENT.name,
          experiment_label: EXPERIMENT.label,
          chunk_size_tokens: null,
          chunk_overlap_tokens: 0,
          splitting_method: "semantic",
          token_count_method: "estimated_local_no_tiktoken",
          estimated_tokens: estimateTokenCount(content),
        },
      });
    });
  });

  fs.writeFileSync(path.join(EXPERIMENT_DIR, "chunks.jsonl"), jsonlStringify(rows), "utf8");
  const stats = buildStats(docs, rows);
  fs.writeFileSync(path.join(EXPERIMENT_DIR, "stats.json"), JSON.stringify(stats, null, 2) + "\n", "utf8");

  const manifestPath = path.join(OUTPUT_DIR, "manifest.json");
  mergeManifest(manifestPath, path.basename(INPUT_FILE), docs.length, [
    {
      experiment: EXPERIMENT.name,
      label: EXPERIMENT.label,
      chunk_size_tokens: null,
      chunk_overlap_tokens: 0,
      splitting_method: "semantic",
      chunk_count: rows.length,
      chunks_file: path.join("outputs", "chunking_experiments", EXPERIMENT.name, "chunks.jsonl"),
      stats_file: path.join("outputs", "chunking_experiments", EXPERIMENT.name, "stats.json"),
      embeddings_file: path.join("outputs", "chunking_experiments", EXPERIMENT.name, "embeddings.jsonl"),
    },
  ]);

  console.log(`${EXPERIMENT.name}: ${rows.length} chunks`);
  console.log(`Updated ${path.join("outputs", "chunking_experiments", "manifest.json")}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
