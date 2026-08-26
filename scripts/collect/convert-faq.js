// 학사 FAQ 원본을 기존 코퍼스와 같은 형식으로 변환한다.
//
//   node scripts/collect/fetch-faq.js      먼저 수집
//   node scripts/collect/convert-faq.js    그다음 변환
//
// 기존 문서 형식
//   page_content: "제목: ...\n출처: ...\n분류: ...\n작성일: YYYY-MM-DD\n\n<본문>"
//   metadata: { id, source, sourceUrl, title, author, published_at, category, crawled_at }
//
// 게시판 글과 다른 점
//   작성일이 없다. FAQ 는 특정 날짜의 공지가 아니라 상시 안내라서 사이트가 날짜를 주지 않는다.
//   published_at 을 null 로 두면 importance.js 의 decayFor 가 0 을 돌려주므로
//   시간 감쇠를 받지 않는다. 해마다 갱신되는 공지와 달리 FAQ 는 늙지 않는 편이 맞다.
//   그래서 page_content 헤더에도 '작성일' 줄을 넣지 않는다.
//   (없는 날짜를 '미상' 같은 말로 채우면 그 말이 임베딩에 섞인다.)
const fs = require("fs");
const path = require("path");

const IN = path.join(process.cwd(), "outputs", "faq_raw.json");
const OUT = path.join(process.cwd(), "outputs", "faq_converted.json");
const TODAY = new Date().toISOString().slice(0, 10);

// FAQ 페이지 구분 -> 기존 코퍼스 분류 11종 중 하나.
//
// 페이지 단위로 매긴다. 항목마다 키워드로 다시 판정하지 않는다.
// 사이트가 이미 주제별로 4개 페이지에 나눠 놓았고, 그 구분이 우리 분류와 거의 맞는다.
// 경계에 걸치는 항목이 두엇 있다('증명서 발급'은 행정·안내에 가깝고
// '군복무학점인정'은 학적·졸업에 가깝다). 그래도 페이지 구분을 그대로 쓴다.
// 분류는 현재 검색 필터로 쓰이지 않아서(query-planner 의 planToFilters 참고)
// 몇 건의 경계 오차보다 규칙이 단순하고 추적 가능한 쪽이 낫다.
const SECTION_CATEGORY = {
  "학적 및 휴복학": "학적·졸업",
  "수강신청": "수업",
  "학점인정": "수업",
  "장학금 및 등록금": "장학금",
};

const SOURCE = "학사FAQ";

function slugify(section) {
  return section.replace(/\s+/gu, "-");
}

function main() {
  if (!fs.existsSync(IN)) {
    console.error(`${path.relative(process.cwd(), IN)} 가 없다. 먼저 fetch-faq.js 를 실행한다.`);
    process.exit(1);
  }

  const raw = JSON.parse(fs.readFileSync(IN, "utf8"));
  const docs = [];
  const skipped = [];
  const seen = new Map();
  const counters = {};

  for (const item of raw) {
    const category = SECTION_CATEGORY[item.section];
    if (!category) {
      skipped.push(`${item.question.slice(0, 30)} (분류 미정: ${item.section})`);
      continue;
    }

    const title = item.question.replace(/\s+/gu, " ").trim();
    const body = item.answer.trim();

    // 답이 사실상 비어 있으면 넣지 않는다. 검색에 걸려도 답할 내용이 없다.
    if (body.length < 10) {
      skipped.push(`${title.slice(0, 30)} (답변 ${body.length}자)`);
      continue;
    }

    // 같은 질문이 여러 페이지에 중복으로 올라와 있을 수 있다.
    const key = title;
    if (seen.has(key)) {
      skipped.push(`${title.slice(0, 30)} (중복, 먼저 나온 것은 ${seen.get(key)})`);
      continue;
    }
    seen.set(key, item.section);

    counters[item.section] = (counters[item.section] || 0) + 1;
    const id = `kumoh-faq-${slugify(item.section)}-${String(counters[item.section]).padStart(2, "0")}`;

    const header = [`제목: ${title}`, `출처: ${SOURCE}`, `분류: ${category}`].join("\n");

    docs.push({
      page_content: `${header}\n\n${body}`,
      metadata: {
        id,
        source: SOURCE,
        sourceUrl: item.source_url,
        title,
        author: "대학본부",
        published_at: null,
        category,
        crawled_at: TODAY,
        // 어느 FAQ 페이지에서 왔는지 남긴다. 나중에 다시 받을 때 대조하기 위해서다.
        faq_section: item.section,
      },
    });
  }

  fs.writeFileSync(OUT, JSON.stringify(docs, null, 2), "utf8");

  console.log(`변환 ${docs.length}건 -> ${path.relative(process.cwd(), OUT)}`);
  const byCategory = {};
  for (const d of docs) byCategory[d.metadata.category] = (byCategory[d.metadata.category] || 0) + 1;
  console.log("\n분류별");
  for (const [k, v] of Object.entries(byCategory)) console.log(`  ${k.padEnd(10)} ${v}건`);

  const lengths = docs.map((d) => d.page_content.length);
  console.log(
    `\n문서 길이  최소 ${Math.min(...lengths)}자 · 최대 ${Math.max(...lengths)}자 · 평균 ${Math.round(lengths.reduce((a, b) => a + b, 0) / lengths.length)}자`
  );

  if (skipped.length) {
    console.log(`\n제외 ${skipped.length}건`);
    skipped.forEach((s) => console.log(`  - ${s}`));
  }
}

main();
