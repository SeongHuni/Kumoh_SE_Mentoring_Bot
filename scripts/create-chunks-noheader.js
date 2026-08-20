// 헤더 제거 대조 실험.
//
// 가설: 이 파이프라인에서 overlap이 효과가 없는 이유는, 모든 청크에 붙는
// 헤더(제목/출처/분류/작성일)가 이미 문맥 보존 역할을 하고 있기 때문이다.
//
// 검증: 헤더를 뺀 상태에서 overlap의 효과를 측정한다. 2x2 설계다.
//
//                  overlap 0        overlap 50
//   헤더 있음      D_500            K_500_ov50          (기존 산출물)
//   헤더 없음      N_500_nohdr      O_500_nohdr_ov50    (이 스크립트)
//
// 헤더가 overlap을 대체하고 있었다면, 헤더가 없을 때 overlap의 이득이 크게 나타나야 한다.
const fs = require("fs");
const path = require("path");
const {
  ensureDir,
  jsonlStringify,
  percentile,
  countBy,
  estimateTokenCount,
  stripExistingHeader,
  mergeManifest,
} = require("./lib/chunking-common");
const { splitWithOverlap, CHUNK_SIZE_TOKENS } = require("./create-chunks-overlap");

const ROOT = process.cwd();
const INPUT_FILE = path.join(ROOT, "data", "document통합파일(에타리뷰분리).json");
const OUTPUT_DIR = path.join(ROOT, "outputs", "chunking_experiments");

const EXPERIMENTS = [
  { name: "N_500_nohdr", label: "N", overlapTokens: 0, meaning: "500 tokens, 헤더 없음, overlap 0" },
  { name: "O_500_nohdr_ov50", label: "O", overlapTokens: 50, meaning: "500 tokens, 헤더 없음, overlap 50" },
];

function makeChunksForExperiment(docs, experiment) {
  const rows = [];

  for (const doc of docs) {
    const metadata = doc.metadata || {};
    const originalId = metadata.id || `doc-${rows.length}`;
    const body = stripExistingHeader(doc.page_content);
    const bodyChunks = splitWithOverlap(body, CHUNK_SIZE_TOKENS, experiment.overlapTokens);

    bodyChunks.forEach((bodyChunk, index) => {
      // 헤더를 붙이지 않는다. 이것이 이 실험의 유일한 조작 변인이다.
      const content = bodyChunk.trim();
      if (!content) return;
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
          chunk_size_tokens: CHUNK_SIZE_TOKENS,
          chunk_overlap_tokens: experiment.overlapTokens,
          splitting_method: "fixed_size_no_header",
          header_included: false,
          token_count_method: "estimated_local_no_tiktoken",
          estimated_tokens: estimateTokenCount(content),
        },
      });
    });
  }

  return rows;
}

function buildStats(docs, chunks, experiment) {
  const tokenCounts = chunks.map((c) => c.metadata.estimated_tokens);
  const perDoc = Object.values(countBy(chunks, (c) => c.metadata.original_id));

  return {
    experiment: experiment.name,
    experiment_label: experiment.label,
    meaning: experiment.meaning,
    source_file: path.basename(INPUT_FILE),
    document_count: docs.length,
    chunk_count: chunks.length,
    chunk_size_tokens: CHUNK_SIZE_TOKENS,
    chunk_overlap_tokens: experiment.overlapTokens,
    splitting_method: "fixed_size_no_header",
    header_included: false,
    estimated_tokens: {
      total: tokenCounts.reduce((a, b) => a + b, 0),
      min: Math.min(...tokenCounts),
      median: percentile(tokenCounts, 0.5),
      p90: percentile(tokenCounts, 0.9),
      max: Math.max(...tokenCounts),
    },
    chunks_per_document: {
      min: Math.min(...perDoc),
      median: percentile(perDoc, 0.5),
      max: Math.max(...perDoc),
    },
    created_at: new Date().toISOString(),
  };
}

function main() {
  ensureDir(OUTPUT_DIR);
  const docs = JSON.parse(fs.readFileSync(INPUT_FILE, "utf8"));
  const entries = [];

  for (const experiment of EXPERIMENTS) {
    const dir = path.join(OUTPUT_DIR, experiment.name);
    ensureDir(dir);

    const chunks = makeChunksForExperiment(docs, experiment);
    const stats = buildStats(docs, chunks, experiment);

    fs.writeFileSync(path.join(dir, "chunks.jsonl"), jsonlStringify(chunks), "utf8");
    fs.writeFileSync(path.join(dir, "stats.json"), JSON.stringify(stats, null, 2) + "\n", "utf8");

    entries.push({
      experiment: experiment.name,
      label: experiment.label,
      chunk_size_tokens: CHUNK_SIZE_TOKENS,
      chunk_overlap_tokens: experiment.overlapTokens,
      splitting_method: "fixed_size_no_header",
      header_included: false,
      chunk_count: chunks.length,
      chunks_file: path.join("outputs", "chunking_experiments", experiment.name, "chunks.jsonl"),
      stats_file: path.join("outputs", "chunking_experiments", experiment.name, "stats.json"),
      embeddings_file: path.join("outputs", "chunking_experiments", experiment.name, "embeddings.jsonl"),
    });

    console.log(
      `${experiment.name}: ${chunks.length} chunks (median ${stats.estimated_tokens.median} tokens)`
    );
  }

  mergeManifest(path.join(OUTPUT_DIR, "manifest.json"), path.basename(INPUT_FILE), docs.length, entries);
  console.log("manifest 갱신 완료");
}

main();
