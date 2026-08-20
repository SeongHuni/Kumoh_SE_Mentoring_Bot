// Overlap 3차 실험 — overlap의 무효 결론이 '청크 크기 500 · fixed-size'에만 국한된 것인지 확인한다.
//
// 기존 실험은 overlap을 500 tokens fixed-size에서만 적용했다(K/L/M/O).
// 여기서는 두 축을 넓힌다.
//
//   신규 실험              비교 대상            검증 축
//   P_recursive_500_ov50   H_recursive_500     splitter 종류 (recursive)
//   Q_300_ov30             C_300               작은 청크 (300)
//   R_1000_ov100           F_1000              큰 청크 (1000)
//
// overlap은 청크 크기의 10%로 통일했다.
const fs = require("fs");
const path = require("path");
const {
  ensureDir,
  jsonlStringify,
  percentile,
  countBy,
  estimateTokenCount,
  hardSplitByTokenEstimate,
  stripExistingHeader,
  buildHeader,
  recursiveSegments,
  mergeManifest,
} = require("./lib/chunking-common");
const { splitNatural, takeOverlapSegments } = require("./create-chunks-overlap");

const ROOT = process.cwd();
const INPUT_FILE = path.join(ROOT, "data", "document통합파일(에타리뷰분리).json");
const OUTPUT_DIR = path.join(ROOT, "outputs", "chunking_experiments");

const EXPERIMENTS = [
  {
    name: "P_recursive_500_ov50",
    label: "P",
    chunkSizeTokens: 500,
    overlapTokens: 50,
    method: "recursive_character_overlap",
    baseline: "H_recursive_500",
    meaning: "Recursive 500 tokens, overlap 50",
  },
  {
    name: "Q_300_ov30",
    label: "Q",
    chunkSizeTokens: 300,
    overlapTokens: 30,
    method: "fixed_size_overlap",
    baseline: "C_300",
    meaning: "Fixed 300 tokens, overlap 30",
  },
  {
    name: "R_1000_ov100",
    label: "R",
    chunkSizeTokens: 1000,
    overlapTokens: 100,
    method: "fixed_size_overlap",
    baseline: "F_1000",
    meaning: "Fixed 1000 tokens, overlap 100",
  },
];

// 조각 목록을 overlap을 두고 청크로 묶는다.
// fixed-size는 splitNatural의 조각을, recursive는 recursiveSegments의 leaf를 넣는다.
// 두 baseline(splitByEstimatedTokens / packLeavesToChunks) 모두 "다음 조각이 안 들어가면 끊는"
// 동일한 그리디 방식이므로, 여기에 carry-over만 더하면 통제된 비교가 된다.
function packWithOverlap(segments, maxTokens, overlapTokens) {
  const chunks = [];
  let current = [];
  let currentTokens = 0;
  let hasNewContent = false;

  const sum = (parts) => parts.reduce((s, p) => s + estimateTokenCount(p), 0);

  const emit = () => {
    const text = current.join("\n").trim();
    if (text && hasNewContent) chunks.push({ text, segments: current });
  };

  for (const segment of segments) {
    const segmentTokens = estimateTokenCount(segment);

    // 조각 하나가 목표 크기를 넘으면 하드 분할한다 (baseline과 동일).
    if (segmentTokens > maxTokens) {
      emit();
      current = [];
      currentTokens = 0;
      hasNewContent = false;

      for (const piece of hardSplitByTokenEstimate(segment, maxTokens)) {
        chunks.push({ text: piece, segments: [piece] });
      }
      const last = chunks[chunks.length - 1];
      current = last ? takeOverlapSegments(last.segments, overlapTokens, maxTokens) : [];
      currentTokens = sum(current);
      continue;
    }

    if (current.length && currentTokens + segmentTokens > maxTokens) {
      emit();
      current = takeOverlapSegments(current, overlapTokens, maxTokens);
      currentTokens = sum(current);
      hasNewContent = false;
    }

    current.push(segment);
    currentTokens += segmentTokens;
    hasNewContent = true;
  }

  emit();
  return chunks.map((c) => c.text);
}

function makeChunks(docs, experiment) {
  const rows = [];

  for (const doc of docs) {
    const metadata = doc.metadata || {};
    const originalId = metadata.id || `doc-${rows.length}`;
    const header = buildHeader(metadata);
    const body = stripExistingHeader(doc.page_content);

    // splitter 종류에 따라 조각 만드는 방식만 다르고, 이후 패킹은 동일하다.
    const segments =
      experiment.method === "recursive_character_overlap"
        ? recursiveSegments(body, experiment.chunkSizeTokens)
        : splitNatural(body);

    const bodyChunks = packWithOverlap(segments, experiment.chunkSizeTokens, experiment.overlapTokens);

    bodyChunks.forEach((bodyChunk, index) => {
      const content = header ? `${header}\n\n${bodyChunk}`.trim() : bodyChunk.trim();
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
          chunk_size_tokens: experiment.chunkSizeTokens,
          chunk_overlap_tokens: experiment.overlapTokens,
          splitting_method: experiment.method,
          baseline_experiment: experiment.baseline,
          token_count_method: "estimated_local_no_tiktoken",
          estimated_tokens: estimateTokenCount(content),
        },
      });
    });
  }

  return rows;
}

function buildStats(docs, chunks, experiment) {
  const tokens = chunks.map((c) => c.metadata.estimated_tokens);
  const perDoc = Object.values(countBy(chunks, (c) => c.metadata.original_id));

  return {
    experiment: experiment.name,
    experiment_label: experiment.label,
    meaning: experiment.meaning,
    baseline_experiment: experiment.baseline,
    splitting_method: experiment.method,
    source_file: path.basename(INPUT_FILE),
    document_count: docs.length,
    chunk_count: chunks.length,
    chunk_size_tokens: experiment.chunkSizeTokens,
    chunk_overlap_tokens: experiment.overlapTokens,
    token_count_method: "estimated_local_no_tiktoken",
    estimated_tokens: {
      total: tokens.reduce((a, b) => a + b, 0),
      min: Math.min(...tokens),
      median: percentile(tokens, 0.5),
      p90: percentile(tokens, 0.9),
      max: Math.max(...tokens),
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

    const chunks = makeChunks(docs, experiment);
    const stats = buildStats(docs, chunks, experiment);

    fs.writeFileSync(path.join(dir, "chunks.jsonl"), jsonlStringify(chunks), "utf8");
    fs.writeFileSync(path.join(dir, "stats.json"), JSON.stringify(stats, null, 2) + "\n", "utf8");

    entries.push({
      experiment: experiment.name,
      label: experiment.label,
      chunk_size_tokens: experiment.chunkSizeTokens,
      chunk_overlap_tokens: experiment.overlapTokens,
      splitting_method: experiment.method,
      baseline_experiment: experiment.baseline,
      chunk_count: chunks.length,
      chunks_file: path.join("outputs", "chunking_experiments", experiment.name, "chunks.jsonl"),
      stats_file: path.join("outputs", "chunking_experiments", experiment.name, "stats.json"),
      embeddings_file: path.join("outputs", "chunking_experiments", experiment.name, "embeddings.jsonl"),
    });

    console.log(
      `${experiment.name.padEnd(22)} ${String(chunks.length).padStart(5)} chunks ` +
        `(baseline ${experiment.baseline}, median ${stats.estimated_tokens.median} tok)`
    );
  }

  mergeManifest(path.join(OUTPUT_DIR, "manifest.json"), path.basename(INPUT_FILE), docs.length, entries);
  console.log("manifest 갱신 완료");
}

main();
