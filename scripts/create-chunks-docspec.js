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
  splitBlankParagraph,
  splitNewline,
  splitInlineMarkers,
  splitSentences,
  makeKeywordAnchorTier,
  recursiveSegments,
  packLeavesToChunks,
  mergeManifest,
} = require("./lib/chunking-common");

const ROOT = process.cwd();
const INPUT_FILE = path.join(ROOT, "data", "document통합파일(에타리뷰분리).json");
const OUTPUT_DIR = path.join(ROOT, "outputs", "chunking_experiments");
const EXPERIMENT = { name: "I_docspec", label: "I", meaning: "Document-Specific Splitting (출처+카테고리 규칙 기반)" };

const EVERYTIME_THRESHOLD = 400;
const SESITE_TARGET_TOKENS = 350;
const SITE_THRESHOLD = 600;
const MAX_MERGED_TOKENS = 900;

const ADMIN_KEYWORDS = /(신청\s*기간|접수\s*기간|신청\s*대상|지원\s*대상|신청\s*방법|제출\s*서류|문의처|담당자|유의사항)/u;
const ADMIN_KEYWORD_TIER = makeKeywordAnchorTier("admin_keyword", ADMIN_KEYWORDS);

// Same tier order as the default recursive splitter, but with an admin-keyword tier
// inserted before inline_marker so labeled administrative fields win as boundaries even
// when they're not phrased as a numbered/lettered list.
const SEGEBOARD_TIERS = [
  { name: "blank_paragraph", split: splitBlankParagraph },
  { name: "newline", split: splitNewline },
  ADMIN_KEYWORD_TIER,
  { name: "inline_marker", split: splitInlineMarkers },
  { name: "sentence", split: splitSentences },
];

// Course reviews are short, single-judgment text — skip the inline_marker tier entirely
// so an incidental number in review text ("3학점짜리라") never gets mistaken for a list.
const EVERYTIME_TIERS = [
  { name: "blank_paragraph", split: splitBlankParagraph },
  { name: "newline", split: splitNewline },
  { name: "sentence", split: splitSentences },
];

const GROUP_PROCEDURAL = ["기간", "대상", "방법", "서류", "문의처"];
const GROUP_EVENT = ["모집대상", "일정", "링크", "담당자"];

// Returns fine-grained leaves (NOT yet packed into size-bounded chunks) so the category
// overlay below can merge semantically-related leaves (e.g. a "신청기간" leaf with a
// "신청방법" leaf) BEFORE final packing. Packing first would risk agglomerating leaves by
// size alone, which can separate related fields into different pre-packed blocks and
// leave the overlay nothing meaningful left to merge.
function sourceLevelLeaves(source, body) {
  if (source === "에브리타임") {
    if (estimateTokenCount(body) <= EVERYTIME_THRESHOLD) return [body];
    return recursiveSegments(body, EVERYTIME_THRESHOLD, 0, EVERYTIME_TIERS);
  }

  if (source === "se게시판") {
    return recursiveSegments(body, SESITE_TARGET_TOKENS, 0, SEGEBOARD_TIERS);
  }

  // 학과공식사이트: each of the 7 docs is already single-topic (verified by inspection),
  // so this reduces to "keep whole unless too long" — no bespoke heading-based splitter.
  if (estimateTokenCount(body) <= SITE_THRESHOLD) return [body];
  return recursiveSegments(body, SITE_THRESHOLD);
}

function baseTargetForSource(source) {
  if (source === "에브리타임") return EVERYTIME_THRESHOLD;
  if (source === "se게시판") return SESITE_TARGET_TOKENS;
  return SITE_THRESHOLD;
}

// Merges consecutive units whose leading text names a field in `keywords` into a single
// unit (up to maxMergedTokens), so e.g. "신청기간: ..." and "신청방법: ..." stay together
// even if the source-level split separated them. Units that don't match a keyword are
// left as-is and also flush any in-progress merge bucket.
function mergeKeepTogether(units, keywords, maxMergedTokens) {
  const belongs = (unit) => keywords.some((kw) => unit.slice(0, 40).includes(kw));
  const result = [];
  let bucket = [];
  let bucketTokens = 0;

  function flush() {
    if (bucket.length) {
      result.push(bucket.join("\n"));
      bucket = [];
      bucketTokens = 0;
    }
  }

  for (const unit of units) {
    if (belongs(unit)) {
      const tokens = estimateTokenCount(unit);
      if (bucket.length && bucketTokens + tokens > maxMergedTokens) flush();
      bucket.push(unit);
      bucketTokens += tokens;
    } else {
      flush();
      result.push(unit);
    }
  }
  flush();
  return result;
}

function docSpecificChunks(doc) {
  const metadata = doc.metadata || {};
  const body = stripExistingHeader(doc.page_content);

  // 강의평 (always 에브리타임): one review = one judgment unit, never split, no cap.
  if (metadata.category === "강의평") return [body];

  const leaves = sourceLevelLeaves(metadata.source, body);
  let overlaid = leaves;
  let packCap = baseTargetForSource(metadata.source);

  if (["수업", "학적·졸업", "장학금"].includes(metadata.category)) {
    overlaid = mergeKeepTogether(leaves, GROUP_PROCEDURAL, MAX_MERGED_TOKENS);
    packCap = MAX_MERGED_TOKENS;
  } else if (["비교과·행사", "연구·캡스톤", "취업·진로"].includes(metadata.category)) {
    overlaid = mergeKeepTogether(leaves, GROUP_EVENT, MAX_MERGED_TOKENS);
    packCap = MAX_MERGED_TOKENS;
  }
  // 학생회/행정·안내/기타: no overlay, pack at the source-level target.

  return packLeavesToChunks(overlaid, packCap);
}

function makeChunksForExperiment(docs) {
  const rows = [];

  for (const doc of docs) {
    const metadata = doc.metadata || {};
    const originalId = metadata.id || `doc-${rows.length}`;
    const header = buildHeader(metadata);
    const bodyChunks = docSpecificChunks(doc);

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
          splitting_method: "document_specific",
          token_count_method: "estimated_local_no_tiktoken",
          estimated_tokens: estimateTokenCount(content),
        },
      });
    });
  }

  return rows;
}

function buildStats(docs, chunks) {
  const tokenCounts = chunks.map((chunk) => chunk.metadata.estimated_tokens);
  const chunksPerDoc = Object.values(countBy(chunks, (chunk) => chunk.metadata.original_id));

  return {
    experiment: EXPERIMENT.name,
    experiment_label: EXPERIMENT.label,
    meaning: EXPERIMENT.meaning,
    splitting_method: "document_specific",
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

function main() {
  ensureDir(OUTPUT_DIR);
  const docs = JSON.parse(fs.readFileSync(INPUT_FILE, "utf8"));
  if (!Array.isArray(docs)) {
    throw new Error("Input file must contain a JSON array.");
  }

  const experimentDir = path.join(OUTPUT_DIR, EXPERIMENT.name);
  ensureDir(experimentDir);

  const chunks = makeChunksForExperiment(docs);
  const stats = buildStats(docs, chunks);

  fs.writeFileSync(path.join(experimentDir, "chunks.jsonl"), jsonlStringify(chunks), "utf8");
  fs.writeFileSync(path.join(experimentDir, "stats.json"), JSON.stringify(stats, null, 2) + "\n", "utf8");

  const manifestPath = path.join(OUTPUT_DIR, "manifest.json");
  mergeManifest(manifestPath, path.basename(INPUT_FILE), docs.length, [
    {
      experiment: EXPERIMENT.name,
      label: EXPERIMENT.label,
      chunk_size_tokens: null,
      chunk_overlap_tokens: 0,
      splitting_method: "document_specific",
      chunk_count: chunks.length,
      chunks_file: path.join("outputs", "chunking_experiments", EXPERIMENT.name, "chunks.jsonl"),
      stats_file: path.join("outputs", "chunking_experiments", EXPERIMENT.name, "stats.json"),
      embeddings_file: path.join("outputs", "chunking_experiments", EXPERIMENT.name, "embeddings.jsonl"),
    },
  ]);

  console.log(`${EXPERIMENT.name}: ${chunks.length} chunks`);
  console.log(`Updated ${path.join("outputs", "chunking_experiments", "manifest.json")}`);
}

main();
