const fs = require("fs");
const path = require("path");
const { readApiKey, chatJson } = require("./lib/rag-core");

const ROOT = process.cwd();
const OUTPUT_DIR = path.join(ROOT, "outputs", "golden_set");
const GOLDEN_FILE = path.join(OUTPUT_DIR, "golden_questions.jsonl");
const SAMPLING_MANIFEST_FILE = path.join(OUTPUT_DIR, "sampling_manifest.json");
const SPOT_CHECK_FILE = path.join(OUTPUT_DIR, "spot_check_sample.md");
const CHAT_MODEL = process.env.OPENAI_CHAT_MODEL || "gpt-4o-mini";

// Scaled from the plan doc's category weight table (sum 78) up to N=80, with the +2
// remainder added to the two largest categories (수업/행정·안내).
const CATEGORY_TARGETS = {
  수업: 13,
  "행정·안내": 11,
  강의평: 10,
  "학적·졸업": 8,
  장학금: 8,
  "비교과·행사": 8,
  "취업·진로": 6,
  "연구·캡스톤": 6,
  학생회: 5,
  대학원: 3,
  기타: 2,
};

function readJsonl(filePath) {
  return fs
    .readFileSync(filePath, "utf8")
    .split(/\r?\n/u)
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

function appendJsonl(filePath, row) {
  fs.appendFileSync(filePath, `${JSON.stringify(row)}\n`, "utf8");
}

function shuffle(array) {
  const result = [...array];
  for (let i = result.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}

// Prefer longer documents (procedural/long-tail docs are where chunking strategies
// actually differ, per the token-distribution finding), without fully excluding short
// ones — take the top 60% by length as the sampling pool, falling back to all docs if
// the category is too small for that pool to cover the target count.
function samplePool(docsInCategory, targetCount) {
  const sorted = [...docsInCategory].sort((a, b) => b.metadata.estimated_tokens - a.metadata.estimated_tokens);
  const poolSize = Math.max(targetCount, Math.ceil(sorted.length * 0.6));
  return sorted.slice(0, Math.min(poolSize, sorted.length));
}

function buildGenerationPrompt(doc) {
  const meta = doc.metadata;
  const system =
    "당신은 대학 학과 챗봇 평가를 위한 테스트 질문 생성기입니다. 주어진 문서 내용만 보고, " +
    "그 문서 내용만으로 답할 수 있는 자연스러운 한국어 질문 1개와 참고 답변을 만드세요. " +
    "질문 유형은 단일사실, 절차, 조건, 비교, 최신성, 링크요구 중 하나를 고르세요. " +
    "질문은 문서 밖의 정보를 요구해서는 안 됩니다. " +
    '다음 JSON 스키마로만 응답하세요: {"question": "...", "question_type": "단일사실|절차|조건|비교|최신성|링크요구", ' +
    '"reference_answer": "...", "expected_evidence": ["..."], "answer_checkpoints": ["..."]}';

  const user =
    `문서 메타데이터:\n제목: ${meta.title}\n출처: ${meta.source}\n분류: ${meta.category}\n` +
    `작성일: ${meta.published_at || ""}\n출처URL: ${meta.sourceUrl || ""}\n\n문서 본문:\n${doc.page_content}`;

  return { system, user };
}

async function main() {
  const experimentsDir = path.join(ROOT, "outputs", "chunking_experiments");
  const docs = readJsonl(path.join(experimentsDir, "A_document", "chunks.jsonl"));

  const byCategory = {};
  for (const doc of docs) {
    const category = doc.metadata.category || "(missing)";
    if (!byCategory[category]) byCategory[category] = [];
    byCategory[category].push(doc);
  }

  const sampled = [];
  const samplingManifest = { targets: CATEGORY_TARGETS, categories: {}, created_at: new Date().toISOString() };

  for (const [category, target] of Object.entries(CATEGORY_TARGETS)) {
    const docsInCategory = byCategory[category] || [];
    if (!docsInCategory.length) {
      console.warn(`No documents found for category "${category}", skipping.`);
      samplingManifest.categories[category] = { target, sampled_count: 0, sampled_ids: [] };
      continue;
    }

    const pool = samplePool(docsInCategory, target);
    const picked = shuffle(pool).slice(0, Math.min(target, pool.length));
    if (picked.length < target) {
      console.warn(`Category "${category}" only has ${picked.length}/${target} available docs.`);
    }

    sampled.push(...picked);
    samplingManifest.categories[category] = {
      target,
      sampled_count: picked.length,
      sampled_ids: picked.map((d) => d.metadata.original_id),
    };
  }

  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  fs.writeFileSync(SAMPLING_MANIFEST_FILE, `${JSON.stringify(samplingManifest, null, 2)}\n`, "utf8");

  const alreadyGenerated = fs.existsSync(GOLDEN_FILE)
    ? new Set(readJsonl(GOLDEN_FILE).map((row) => row.gold_doc_ids[0]))
    : new Set();

  const apiKey = readApiKey();
  const generated = fs.existsSync(GOLDEN_FILE) ? readJsonl(GOLDEN_FILE) : [];

  console.log(`Golden set target: ${sampled.length} questions (${alreadyGenerated.size} already generated)`);

  for (let i = 0; i < sampled.length; i += 1) {
    const doc = sampled[i];
    const originalId = doc.metadata.original_id;
    if (alreadyGenerated.has(originalId)) continue;

    const prompt = buildGenerationPrompt(doc);
    const parsed = await chatJson(apiKey, CHAT_MODEL, prompt);

    const row = {
      question: parsed.question,
      gold_doc_ids: [originalId],
      gold_category: doc.metadata.category,
      expected_evidence: parsed.expected_evidence || [],
      answer_checkpoints: parsed.answer_checkpoints || [],
      question_type: parsed.question_type,
      reference_answer: parsed.reference_answer,
      source_chunk_id: doc.metadata.chunk_id,
      generated_by_model: CHAT_MODEL,
      generated_at: new Date().toISOString(),
    };

    appendJsonl(GOLDEN_FILE, row);
    generated.push(row);
    console.log(`  [${i + 1}/${sampled.length}] (${doc.metadata.category}) ${row.question}`);
  }

  const spotCheckCount = Math.max(1, Math.round(generated.length * 0.18));
  const spotCheckSample = shuffle(generated).slice(0, spotCheckCount);
  const spotCheckMd = [
    `# Golden Set Spot Check Sample (${spotCheckSample.length} / ${generated.length})`,
    "",
    ...spotCheckSample.map(
      (row, i) =>
        `## ${i + 1}. [${row.gold_category}] ${row.question}\n\n` +
        `- gold_doc_ids: ${JSON.stringify(row.gold_doc_ids)}\n` +
        `- question_type: ${row.question_type}\n` +
        `- reference_answer: ${row.reference_answer}\n` +
        `- expected_evidence: ${JSON.stringify(row.expected_evidence)}\n` +
        `- answer_checkpoints: ${JSON.stringify(row.answer_checkpoints)}\n`
    ),
  ].join("\n");

  fs.writeFileSync(SPOT_CHECK_FILE, spotCheckMd, "utf8");

  console.log(`\nTotal golden questions: ${generated.length}`);
  console.log(`Saved: ${path.relative(ROOT, GOLDEN_FILE)}`);
  console.log(`Saved: ${path.relative(ROOT, SAMPLING_MANIFEST_FILE)}`);
  console.log(`Saved: ${path.relative(ROOT, SPOT_CHECK_FILE)} (${spotCheckSample.length} questions for manual review)`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
