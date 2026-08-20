// RAG 질의 CLI.
//   node scripts/ask.js "장학금 신청 조건이 뭐야"
//   node scripts/ask.js "MT 갔었나" --year 2025
//   node scripts/ask.js "수강신청 언제야" --since 2026-01-01 --category 수업 --k 8
const { readApiKey, embedQuery, generateAnswer } = require("./lib/rag-core");
const { openCollection, search, COLLECTION } = require("./lib/chroma-store");

const CHAT_MODEL = process.env.OPENAI_CHAT_MODEL || "gpt-4o-mini";

function parseArgs(argv) {
  const options = { k: 5, filters: {} };
  const words = [];

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (!arg.startsWith("--")) {
      words.push(arg);
      continue;
    }
    const key = arg.slice(2);
    const value = argv[i + 1];
    if (value === undefined || value.startsWith("--")) {
      throw new Error(`--${key} 옵션에 값이 필요합니다.`);
    }
    i += 1;

    if (key === "k") options.k = Number(value);
    else if (["category", "source", "year", "since", "until"].includes(key)) options.filters[key] = value;
    else throw new Error(`알 수 없는 옵션: --${key}`);
  }

  options.question = words.join(" ").trim();
  return options;
}

function buildPrompt(question, retrieved) {
  const context = retrieved
    .map((r, i) => {
      const m = r.metadata;
      const header = [m.title, m.source, m.published_at].filter(Boolean).join(" | ");
      return `[${i + 1}] (${header})\n${r.page_content}`;
    })
    .join("\n\n---\n\n");

  return {
    system:
      "당신은 금오공대 소프트웨어전공 안내 챗봇입니다. 아래 참고 자료만 근거로 답변하세요. " +
      "자료에 근거가 없으면 추측하지 말고 모른다고 답하세요. " +
      "날짜나 학기가 걸린 질문은 자료의 작성일을 확인하고 답하세요. " +
      "본문에서 근거를 쓴 문장 끝마다 [1], [2] 형태로 자료 번호를 표시하세요.",
    user: `질문: ${question}\n\n참고 자료:\n${context}`,
  };
}

async function main() {
  const options = parseArgs(process.argv.slice(2));

  if (!options.question) {
    console.error('사용법: node scripts/ask.js "질문" [--k 5] [--category 장학금] [--source se게시판] [--year 2026] [--since YYYY-MM-DD] [--until YYYY-MM-DD]');
    process.exit(1);
  }

  const apiKey = readApiKey();
  const collection = await openCollection();

  const startedAt = Date.now();
  const queryEmbedding = await embedQuery(apiKey, options.question);
  const embeddedAt = Date.now();

  const retrieved = await search(collection, queryEmbedding, options.k, options.filters);
  const retrievedAt = Date.now();

  if (!retrieved.length) {
    console.log("검색 결과가 없습니다. 필터 조건을 완화해 보세요.");
    return;
  }

  const answer = await generateAnswer(apiKey, CHAT_MODEL, buildPrompt(options.question, retrieved), 0);
  const doneAt = Date.now();

  console.log(`\n질문: ${options.question}`);
  const filterKeys = Object.keys(options.filters);
  if (filterKeys.length) {
    console.log(`필터: ${filterKeys.map((key) => `${key}=${options.filters[key]}`).join(", ")}`);
  }

  console.log(`\n${"=".repeat(70)}\n${answer}\n${"=".repeat(70)}`);

  console.log("\n참고 자료:");
  retrieved.forEach((r, i) => {
    const m = r.metadata;
    console.log(`  [${i + 1}] ${m.title || "(제목 없음)"}`);
    console.log(`      ${m.source || "-"} | ${m.published_at || "날짜 미상"} | 유사도 ${r.score.toFixed(3)}`);
    if (m.source_url) console.log(`      ${m.source_url}`);
  });

  console.log(
    `\n소요: 임베딩 ${embeddedAt - startedAt}ms, 검색 ${retrievedAt - embeddedAt}ms, ` +
      `생성 ${doneAt - retrievedAt}ms (컬렉션 ${COLLECTION}, 모델 ${CHAT_MODEL})`
  );
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
