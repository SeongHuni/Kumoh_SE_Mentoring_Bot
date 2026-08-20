const fs = require("fs");
const path = require("path");

const ROOT = process.cwd();
const INPUT_FILE = path.join(ROOT, "data", "document통합파일(에타리뷰분리).json");
const OUTPUT_DIR = path.join(ROOT, "outputs", "chunking_experiments");

const EXPERIMENTS = [
  { name: "A_document", label: "A", chunkSizeTokens: null, meaning: "Chunking 안 함 (Baseline)" },
  { name: "B_150", label: "B", chunkSizeTokens: 150, meaning: "매우 작은 Chunk" },
  { name: "C_300", label: "C", chunkSizeTokens: 300, meaning: "작은 Chunk" },
  { name: "D_500", label: "D", chunkSizeTokens: 500, meaning: "중간 Chunk" },
  { name: "E_800", label: "E", chunkSizeTokens: 800, meaning: "큰 Chunk" },
  { name: "F_1000", label: "F", chunkSizeTokens: 1000, meaning: "매우 큰 Chunk" },
];

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function jsonlStringify(rows) {
  return rows.map((row) => JSON.stringify(row)).join("\n") + "\n";
}

function estimateTokenCount(text) {
  let total = 0;
  const parts = String(text || "").match(/https?:\/\/\S+|[A-Za-z0-9_]+|\s+|./gsu) || [];

  for (const part of parts) {
    if (/^\s+$/u.test(part)) continue;
    if (/^https?:\/\//u.test(part)) {
      total += Math.max(1, Math.ceil(part.length / 6));
    } else if (/^[A-Za-z0-9_]+$/u.test(part)) {
      total += Math.max(1, Math.ceil(part.length / 4));
    } else if (/^[.,!?;:()[\]{}"'`~@#$%^&*_+=/\\|-]$/u.test(part)) {
      total += 1;
    } else {
      total += Array.from(part).length;
    }
  }

  return total;
}

function stripExistingHeader(pageContent) {
  const text = String(pageContent || "").replace(/\r\n/g, "\n");
  if (!text.startsWith("제목:")) return text.trim();

  const blankLineIndex = text.indexOf("\n\n");
  if (blankLineIndex === -1) return text.trim();
  return text.slice(blankLineIndex + 2).trim();
}

function buildHeader(metadata) {
  const lines = [];
  if (metadata.title) lines.push(`제목: ${metadata.title}`);
  if (metadata.source) lines.push(`출처: ${metadata.source}`);
  if (metadata.category) lines.push(`분류: ${metadata.category}`);
  if (metadata.published_at) lines.push(`작성일: ${metadata.published_at}`);
  return lines.join("\n");
}

function splitNatural(text) {
  const normalized = String(text || "").replace(/\r\n/g, "\n").trim();
  if (!normalized) return [];

  const chunks = [];
  const paragraphs = normalized
    .split(/\n{2,}/u)
    .map((part) => part.trim())
    .filter(Boolean);

  for (const paragraph of paragraphs) {
    const listParts = paragraph
      .split(/\n(?=\s*(?:[-*•◦]|\d+[.)]|[가-하][.)]))/u)
      .map((part) => part.trim())
      .filter(Boolean);

    for (const listPart of listParts) {
      const sentences = listPart
        .replace(/([.!?。！？]|(?:다|요|니다|음|함)\.)\s+/gu, "$1\n")
        .split(/\n+/u)
        .map((part) => part.trim())
        .filter(Boolean);
      chunks.push(...sentences);
    }
  }

  return chunks.length ? chunks : [normalized];
}

function hardSplitByTokenEstimate(text, maxTokens) {
  const parts = String(text || "").match(/https?:\/\/\S+|[A-Za-z0-9_]+|\s+|./gsu) || [];
  const chunks = [];
  let current = "";
  let currentTokens = 0;

  for (const part of parts) {
    const partTokens = estimateTokenCount(part);
    if (current && currentTokens + partTokens > maxTokens) {
      chunks.push(current.trim());
      current = "";
      currentTokens = 0;
    }
    current += part;
    currentTokens += partTokens;
  }

  if (current.trim()) chunks.push(current.trim());
  return chunks;
}

function splitByEstimatedTokens(body, maxTokens) {
  const segments = splitNatural(body);
  const chunks = [];
  let current = "";
  let currentTokens = 0;

  for (const segment of segments) {
    const segmentTokens = estimateTokenCount(segment);

    if (segmentTokens > maxTokens) {
      if (current.trim()) {
        chunks.push(current.trim());
        current = "";
        currentTokens = 0;
      }
      chunks.push(...hardSplitByTokenEstimate(segment, maxTokens));
      continue;
    }

    if (current && currentTokens + segmentTokens > maxTokens) {
      chunks.push(current.trim());
      current = segment;
      currentTokens = segmentTokens;
    } else {
      current = current ? `${current}\n${segment}` : segment;
      currentTokens += segmentTokens;
    }
  }

  if (current.trim()) chunks.push(current.trim());
  return chunks;
}

function percentile(values, p) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor((sorted.length - 1) * p)];
}

function countBy(rows, selector) {
  return rows.reduce((acc, row) => {
    const key = selector(row) || "(missing)";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
}

function makeChunksForExperiment(docs, experiment) {
  const rows = [];

  for (const doc of docs) {
    const metadata = doc.metadata || {};
    const originalId = metadata.id || `doc-${rows.length}`;
    const header = buildHeader(metadata);
    const body = stripExistingHeader(doc.page_content);
    const bodyChunks = experiment.chunkSizeTokens
      ? splitByEstimatedTokens(body, experiment.chunkSizeTokens)
      : [body];

    bodyChunks.forEach((bodyChunk, index) => {
      const content = header ? `${header}\n\n${bodyChunk}`.trim() : bodyChunk.trim();
      rows.push({
        page_content: content,
        metadata: {
          ...metadata,
          original_id: originalId,
          chunk_id: `${originalId}::${experiment.name}::${String(index).padStart(4, "0")}`,
          chunk_index: index,
          chunk_count: bodyChunks.length,
          experiment: experiment.name,
          experiment_label: experiment.label,
          chunk_size_tokens: experiment.chunkSizeTokens,
          chunk_overlap_tokens: 0,
          token_count_method: "estimated_local_no_tiktoken",
          estimated_tokens: estimateTokenCount(content),
        },
      });
    });
  }

  return rows;
}

function buildStats(docs, chunks, experiment) {
  const tokenCounts = chunks.map((chunk) => chunk.metadata.estimated_tokens);
  const chunksPerDoc = Object.values(countBy(chunks, (chunk) => chunk.metadata.original_id));

  return {
    experiment: experiment.name,
    experiment_label: experiment.label,
    meaning: experiment.meaning,
    source_file: path.basename(INPUT_FILE),
    document_count: docs.length,
    chunk_count: chunks.length,
    chunk_size_tokens: experiment.chunkSizeTokens,
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

function main() {
  ensureDir(OUTPUT_DIR);
  const docs = JSON.parse(fs.readFileSync(INPUT_FILE, "utf8"));
  if (!Array.isArray(docs)) {
    throw new Error("Input file must contain a JSON array.");
  }

  const manifest = {
    source_file: path.basename(INPUT_FILE),
    document_count: docs.length,
    experiments: [],
    created_at: new Date().toISOString(),
  };

  for (const experiment of EXPERIMENTS) {
    const experimentDir = path.join(OUTPUT_DIR, experiment.name);
    ensureDir(experimentDir);

    const chunks = makeChunksForExperiment(docs, experiment);
    const stats = buildStats(docs, chunks, experiment);

    fs.writeFileSync(path.join(experimentDir, "chunks.jsonl"), jsonlStringify(chunks), "utf8");
    fs.writeFileSync(path.join(experimentDir, "stats.json"), JSON.stringify(stats, null, 2) + "\n", "utf8");

    manifest.experiments.push({
      experiment: experiment.name,
      label: experiment.label,
      chunk_size_tokens: experiment.chunkSizeTokens,
      chunk_overlap_tokens: 0,
      chunk_count: chunks.length,
      chunks_file: path.join("outputs", "chunking_experiments", experiment.name, "chunks.jsonl"),
      stats_file: path.join("outputs", "chunking_experiments", experiment.name, "stats.json"),
      embeddings_file: path.join("outputs", "chunking_experiments", experiment.name, "embeddings.jsonl"),
    });

    console.log(`${experiment.name}: ${chunks.length} chunks`);
  }

  fs.writeFileSync(path.join(OUTPUT_DIR, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n", "utf8");
  console.log(`Wrote ${path.join("outputs", "chunking_experiments", "manifest.json")}`);
}

main();
