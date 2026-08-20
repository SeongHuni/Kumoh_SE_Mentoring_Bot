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
  recursiveSegments,
  packLeavesToChunks,
  mergeManifest,
} = require("./lib/chunking-common");

const ROOT = process.cwd();
const INPUT_FILE = path.join(ROOT, "data", "document통합파일(에타리뷰분리).json");
const OUTPUT_DIR = path.join(ROOT, "outputs", "chunking_experiments");

// Target sizes match the plan doc's own a-priori leading candidates from phase 1
// (C_300 / D_500), now split with a real separator-tier recursive splitter instead of
// naive token packing.
const EXPERIMENTS = [
  { name: "G_recursive_300", label: "G", chunkSizeTokens: 300, meaning: "Recursive Character Splitting (목표 300 tok)" },
  { name: "H_recursive_500", label: "H", chunkSizeTokens: 500, meaning: "Recursive Character Splitting (목표 500 tok)" },
];

function makeChunksForExperiment(docs, experiment) {
  const rows = [];

  for (const doc of docs) {
    const metadata = doc.metadata || {};
    const originalId = metadata.id || `doc-${rows.length}`;
    const header = buildHeader(metadata);
    const body = stripExistingHeader(doc.page_content);

    const leaves = recursiveSegments(body, experiment.chunkSizeTokens);
    const bodyChunks = packLeavesToChunks(leaves, experiment.chunkSizeTokens);

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
          splitting_method: "recursive_character",
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
    splitting_method: "recursive_character",
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

  const manifestEntries = [];

  for (const experiment of EXPERIMENTS) {
    const experimentDir = path.join(OUTPUT_DIR, experiment.name);
    ensureDir(experimentDir);

    const chunks = makeChunksForExperiment(docs, experiment);
    const stats = buildStats(docs, chunks, experiment);

    fs.writeFileSync(path.join(experimentDir, "chunks.jsonl"), jsonlStringify(chunks), "utf8");
    fs.writeFileSync(path.join(experimentDir, "stats.json"), JSON.stringify(stats, null, 2) + "\n", "utf8");

    manifestEntries.push({
      experiment: experiment.name,
      label: experiment.label,
      chunk_size_tokens: experiment.chunkSizeTokens,
      chunk_overlap_tokens: 0,
      splitting_method: "recursive_character",
      chunk_count: chunks.length,
      chunks_file: path.join("outputs", "chunking_experiments", experiment.name, "chunks.jsonl"),
      stats_file: path.join("outputs", "chunking_experiments", experiment.name, "stats.json"),
      embeddings_file: path.join("outputs", "chunking_experiments", experiment.name, "embeddings.jsonl"),
    });

    console.log(`${experiment.name}: ${chunks.length} chunks`);
  }

  const manifestPath = path.join(OUTPUT_DIR, "manifest.json");
  mergeManifest(manifestPath, path.basename(INPUT_FILE), docs.length, manifestEntries);
  console.log(`Updated ${path.join("outputs", "chunking_experiments", "manifest.json")}`);
}

main();
