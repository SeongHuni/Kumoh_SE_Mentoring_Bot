// 수집한 새 글을 기존 코퍼스와 같은 형식으로 변환한다.
//
//   node scripts/collect/convert-new-posts.js
//
// 기존 문서 형식
//   page_content: "제목: ...\n출처: se게시판\n분류: ...\n작성일: YYYY-MM-DD\n\n<본문>"
//   metadata: { id, source, sourceUrl, title, author, published_at, category, crawled_at }
//
// 분류(category)는 검색 필터에 직접 쓰이므로 기존 11종 체계에 맞춰야 한다.
// 게시판이 주는 분류는 '일반/Archive/학생회' 3종뿐이라 제목 말머리와 본문 키워드로 매핑한다.
const fs = require("fs");
const path = require("path");

const IN = path.join(process.cwd(), "outputs", "new_posts_raw.json");
const OUT = path.join(process.cwd(), "outputs", "new_posts_converted.json");
const TODAY = new Date().toISOString().slice(0, 10);

// 기존 코퍼스가 쓰는 분류 11종
const CATEGORIES = [
  "수업", "장학금", "행정·안내", "학적·졸업", "비교과·행사",
  "취업·진로", "연구·캡스톤", "학생회", "대학원", "강의평", "기타",
];

// 제목 말머리 -> 분류. 기존 코퍼스의 말머리 분포를 보고 정했다.
const PREFIX_MAP = {
  "수업": "수업",
  "장학": "장학금",
  "학적": "학적·졸업",
  "졸업요건": "학적·졸업",
  "대학원": "대학원",
  "학생회": "학생회",
  "교내행사": "비교과·행사",
  "SEcon": "비교과·행사",
  "선거관리위원회": "학생회",
  "대학일자리플러스센터": "취업·진로",
  "국립대학 육성사업": "비교과·행사",
  "캡스톤디자인1": "연구·캡스톤",
  "캡스톤디자인2": "연구·캡스톤",
  "대학본부": "행정·안내",
};

// 말머리로 안 잡힐 때 쓰는 키워드. 위에서부터 먼저 맞는 것을 쓴다.
//
// 순서가 중요하다. 처음엔 '졸업' 이 '졸업생 채용' 공고를 학적·졸업으로,
// '관' 이 '디지털관 쓰레기 배출' 을 연구·캡스톤으로 잘못 잡았다.
// 그래서 (1) 채용을 학적보다 먼저 보고 (2) 학적 키워드에서 '졸업생' 을 제외하고
// (3) 캡스톤 키워드를 좁혔다. 판정은 제목을 본문보다 우선한다.
const KEYWORD_RULES = [
  // 채용 공고는 '졸업생' 같은 단어를 자주 써서 학적보다 먼저 판정한다.
  [/채용|모집 공고|취업|인턴|일자리|진로|연봉/, "취업·진로"],
  [/수강신청|수강지도|공결|출석인정|강의평가|수강꾸러미|계절학기|재수강|학점이월/, "수업"],
  [/장학(금|생)|등록금 감면/, "장학금"],
  [/대학원|석사|박사|학석사/, "대학원"],
  [/학위수여|학위변경|학적|복학|휴학|전과|소속변경|졸업요건|졸업사정/, "학적·졸업"],
  [/캡스톤|졸업작품|연구실|학술|논문/, "연구·캡스톤"],
  [/학생회|과잠|MT|엠티|총회|간식/, "학생회"],
  [/설명회|특강|공모전|대회|부트캠프|멘토링|캠프|참여팀|프로젝트 모집/, "비교과·행사"],
];

function toCategory(post) {
  const title = String(post.title || "");

  const m = title.match(/^\s*\[([^\]]+)\]/u);
  if (m && PREFIX_MAP[m[1].trim()]) return PREFIX_MAP[m[1].trim()];

  if (post.boardCategory === "학생회") return "학생회";

  // 제목이 주제를 가장 잘 나타내므로 제목만으로 먼저 판정한다.
  for (const [re, cat] of KEYWORD_RULES) {
    if (re.test(title)) return cat;
  }
  // 제목으로 못 정하면 본문 앞부분까지 본다.
  const body = stripHtml(post.contents).slice(0, 400);
  for (const [re, cat] of KEYWORD_RULES) {
    if (re.test(body)) return cat;
  }
  return "행정·안내"; // 기존 코퍼스에서 가장 흔한 분류
}

// HTML 본문을 기존 코퍼스와 같은 평문으로 만든다.
// 블록 태그는 공백으로 바꿔 단어가 붙지 않게 하고, 엔티티를 풀고, 공백을 정규화한다.
function stripHtml(html) {
  return String(html || "")
    .replace(/<(script|style)[\s\S]*?<\/\1>/giu, " ")
    .replace(/<br\s*\/?>/giu, " ")
    .replace(/<\/(p|div|li|tr|h[1-6]|table)>/giu, " ")
    .replace(/<[^>]+>/gu, " ")
    .replace(/&nbsp;/giu, " ")
    .replace(/&lt;/giu, "<")
    .replace(/&gt;/giu, ">")
    .replace(/&amp;/giu, "&")
    .replace(/&quot;/giu, '"')
    .replace(/&#39;/giu, "'")
    .replace(/ /gu, " ")
    .replace(/\s+/gu, " ")
    .trim();
}

// 제목 앞 말머리는 metadata.title 에는 남기되 기존 코퍼스와 형태를 맞춘다.
function buildDocument(post) {
  const publishedAt = String(post.createdAt).slice(0, 10);
  const category = toCategory(post);
  const body = stripHtml(post.contents);
  const title = String(post.title || "").trim();

  const header = [
    `제목: ${title}`,
    `출처: se게시판`,
    `분류: ${category}`,
    `작성일: ${publishedAt}`,
  ].join("\n");

  return {
    page_content: `${header}\n\n${body}`,
    metadata: {
      id: `kumoh-notice-${post.postId}`,
      source: "se게시판",
      sourceUrl: `https://seboard.site/notice/${post.postId}`,
      title,
      author: post.author || "[조교]",
      published_at: publishedAt,
      category,
      crawled_at: TODAY,
    },
  };
}

function main() {
  const posts = JSON.parse(fs.readFileSync(IN, "utf8"));

  // 기존 코퍼스에 이미 있는 글은 건너뛴다.
  const existing = new Set(
    JSON.parse(fs.readFileSync(path.join(process.cwd(), "data", "document통합파일(에타리뷰분리).json"), "utf8"))
      .map((d) => d.metadata.id)
  );

  const docs = [];
  const skipped = [];
  for (const p of posts) {
    const id = `kumoh-notice-${p.postId}`;
    if (existing.has(id)) { skipped.push(id); continue; }
    const doc = buildDocument(p);
    if (!doc.page_content.split("\n\n")[1]?.trim()) { skipped.push(`${id}(본문없음)`); continue; }
    docs.push(doc);
  }

  fs.writeFileSync(OUT, JSON.stringify(docs, null, 2), "utf8");

  console.log(`변환 완료: ${docs.length}건  (건너뜀 ${skipped.length}건)`);
  if (skipped.length) console.log(`  건너뜀: ${skipped.join(", ")}`);

  const byCat = {};
  docs.forEach((d) => { byCat[d.metadata.category] = (byCat[d.metadata.category] || 0) + 1; });
  console.log(`\n분류 배분:`);
  Object.entries(byCat).sort((a, b) => b[1] - a[1]).forEach(([k, v]) => console.log(`  ${k.padEnd(10)} ${v}건`));

  console.log(`\n=== 변환 결과 (전체) ===`);
  docs.forEach((d) => {
    const m = d.metadata;
    const body = d.page_content.split("\n\n").slice(1).join(" ");
    console.log(`  ${m.published_at}  [${m.category}] ${m.title.slice(0, 40)}`);
    console.log(`     본문 ${body.length}자: ${body.slice(0, 70)}...`);
  });

  console.log(`\n저장: ${path.relative(process.cwd(), OUT)}`);
}

main();
