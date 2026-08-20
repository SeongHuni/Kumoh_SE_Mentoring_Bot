// 2차 실험: 500 tokens fixed-size로 확정한 뒤 overlap 값만 바꿔 비교한다.
// 분할 로직은 create-chunks.js의 D_500과 동일하게 유지하고, 새 청크를 시작할 때
// 직전 청크의 뒤쪽 segment들을 overlap 토큰만큼 앞에 붙이는 부분만 다르다.
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
  mergeManifest,
} = require("./lib/chunking-common");

const ROOT = process.cwd();
const INPUT_FILE = path.join(ROOT, "data", "document통합파일(에타리뷰분리).json");
const OUTPUT_DIR = path.join(ROOT, "outputs", "chunking_experiments");
const CHUNK_SIZE_TOKENS = 500;

const EXPERIMENTS = [
  { name: "K_500_ov50", label: "K", overlapTokens: 50, meaning: "500 tokens, overlap 50 (10%)" },
  { name: "L_500_ov100", label: "L", overlapTokens: 100, meaning: "500 tokens, overlap 100 (20%)" },
  { name: "M_500_ov150", label: "M", overlapTokens: 150, meaning: "500 tokens, overlap 150 (30%)" },
];

// create-chunks.js의 splitNatural과 동일한 문단/리스트/문장 분해 규칙.
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

// 문장 중간을 자르지 않도록 segment 뒤쪽에서 budget 토큰 이하가 되는
// 최대 길이의 꼬리를 단어 경계 기준으로 잘라낸다.
function tailWithinBudget(segment, budget) {
  const parts = String(segment).match(/https?:\/\/\S+|[A-Za-z0-9_]+|\s+|./gsu) || [];
  let tail = "";
  let total = 0;

  for (let i = parts.length - 1; i >= 0; i -= 1) {
    const partTokens = estimateTokenCount(parts[i]);
    if (total + partTokens > budget) break;
    tail = parts[i] + tail;
    total += partTokens;
  }

  return tail.trim();
}

// 직전 청크를 이룬 segment 목록에서 뒤쪽부터 overlap 토큰만큼 가져온다.
// segment 경계를 우선 지키되, 마지막 segment 하나가 이미 budget보다 크면
// (이 데이터셋의 긴 공지 문단에서 흔하다) 그 segment의 꼬리만 잘라 가져온다.
// budget은 최대 청크 크기의 절반을 넘지 않게 해 overlap이 본문을 밀어내지 않게 한다.
function takeOverlapSegments(segments, overlapTokens, maxTokens) {
  if (overlapTokens <= 0 || !segments.length) return [];

  const budget = Math.min(overlapTokens, Math.floor(maxTokens / 2));
  const taken = [];
  let total = 0;

  for (let i = segments.length - 1; i >= 0; i -= 1) {
    const segmentTokens = estimateTokenCount(segments[i]);
    if (total + segmentTokens > budget) break;
    taken.unshift(segments[i]);
    total += segmentTokens;
  }

  if (taken.length) return taken;

  const tail = tailWithinBudget(segments[segments.length - 1], budget);
  return tail ? [tail] : [];
}

function splitWithOverlap(body, maxTokens, overlapTokens) {
  const segments = splitNatural(body);
  const chunks = [];

  let current = [];
  let currentTokens = 0;
  // 마지막 flush 이후 새 segment가 들어왔는지. overlap 부분만 남은 상태에서
  // 다시 flush하면 직전 청크의 부분집합인 중복 청크가 생기므로 이를 막는다.
  let hasNewContent = false;

  const sumTokens = (parts) => parts.reduce((sum, part) => sum + estimateTokenCount(part), 0);

  const emit = () => {
    const text = current.join("\n").trim();
    if (text && hasNewContent) chunks.push({ text, segments: current });
    return text;
  };

  const flush = () => {
    emit();
    const carried = takeOverlapSegments(current, overlapTokens, maxTokens);
    current = carried;
    currentTokens = sumTokens(carried);
    hasNewContent = false;
  };

  for (const segment of segments) {
    const segmentTokens = estimateTokenCount(segment);

    // 단일 segment가 목표 크기를 넘으면 하드 분할한다 (D_500과 동일).
    if (segmentTokens > maxTokens) {
      emit();
      current = [];
      currentTokens = 0;
      hasNewContent = false;

      for (const piece of hardSplitByTokenEstimate(segment, maxTokens)) {
        chunks.push({ text: piece, segments: [piece] });
      }

      // 하드 분할 직후에도 마지막 조각의 꼬리를 overlap으로 이어받는다.
      const last = chunks[chunks.length - 1];
      current = last ? takeOverlapSegments(last.segments, overlapTokens, maxTokens) : [];
      currentTokens = sumTokens(current);
      continue;
    }

    if (current.length && currentTokens + segmentTokens > maxTokens) {
      flush();
    }

    current.push(segment);
    currentTokens += segmentTokens;
    hasNewContent = true;
  }

  emit();
  return chunks.map((chunk) => chunk.text);
}

function makeChunksForExperiment(docs, experiment) {
  const rows = [];

  for (const doc of docs) {
    const metadata = doc.metadata || {};
    const originalId = metadata.id || `doc-${rows.length}`;
    const header = buildHeader(metadata);
    const body = stripExistingHeader(doc.page_content);
    const bodyChunks = splitWithOverlap(body, CHUNK_SIZE_TOKENS, experiment.overlapTokens);

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
          chunk_size_tokens: CHUNK_SIZE_TOKENS,
          chunk_overlap_tokens: experiment.overlapTokens,
          splitting_method: "fixed_size_overlap",
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
    chunk_size_tokens: CHUNK_SIZE_TOKENS,
    chunk_overlap_tokens: experiment.overlapTokens,
    splitting_method: "fixed_size_overlap",
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
      chunk_size_tokens: CHUNK_SIZE_TOKENS,
      chunk_overlap_tokens: experiment.overlapTokens,
      splitting_method: "fixed_size_overlap",
      chunk_count: chunks.length,
      chunks_file: path.join("outputs", "chunking_experiments", experiment.name, "chunks.jsonl"),
      stats_file: path.join("outputs", "chunking_experiments", experiment.name, "stats.json"),
      embeddings_file: path.join("outputs", "chunking_experiments", experiment.name, "embeddings.jsonl"),
    });

    console.log(
      `${experiment.name}: ${chunks.length} chunks (median ${stats.estimated_tokens.median} tokens)`
    );
  }

  mergeManifest(path.join(OUTPUT_DIR, "manifest.json"), path.basename(INPUT_FILE), docs.length, manifestEntries);
  console.log(`Updated ${path.join("outputs", "chunking_experiments", "manifest.json")}`);
}

// 헤더 제거 대조 실험(create-chunks-noheader.js)이 같은 분할 로직을 재사용하도록 내보낸다.
module.exports = { splitNatural, splitWithOverlap, takeOverlapSegments, CHUNK_SIZE_TOKENS };

if (require.main === module) main();
