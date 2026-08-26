// 대학 학사 FAQ 4개 페이지를 받아 질문·답변 쌍으로 뽑는다.
//
//   node scripts/collect/fetch-faq.js
//
// 왜 필요한가
//   학과 게시판에는 휴학·복학·자퇴 절차 문서가 없다(제목 0건, '자퇴'는 본문에도 0건).
//   그래서 "휴학 전에 지도교수 상담이 필요한가요?" 같은 질문에 답할 근거가 없었다.
//   학사 FAQ에 그 내용이 있어서 가져온다.
//
// 파싱에서 조심할 것 두 가지
//   (1) <dt>/<dd> 를 문서 전체에서 순서대로 짝지으면 안 된다.
//       페이지에는 네비게이션·로그인 영역에도 <dt>/<dd> 가 있어서
//       그렇게 하면 질문과 답이 한 칸씩 밀려 붙는다. 실제로 처음에 그렇게 됐다.
//       FAQ 한 항목은 <dl> 하나이므로 <dl> 단위로 잘라서 그 안에서 짝짓는다.
//
//   (2) 기본 목록은 10개씩 끊겨 나온다. 수강신청은 총 13건이라 3건을 놓친다.
//       ?articleLimit=200 으로 한 번에 받는다.
const fs = require("fs");
const path = require("path");

const OUT = path.join(process.cwd(), "outputs", "faq_raw.json");

const PAGES = [
  { code: "01", label: "학적 및 휴복학" },
  { code: "02", label: "수강신청" },
  { code: "03", label: "학점인정" },
  { code: "04", label: "장학금 및 등록금" },
];

const url = (code) =>
  `https://www.kumoh.ac.kr/ko/sub02_03_02_${code}.do?mode=list&articleLimit=200&article.offset=0`;

// ------------------------------------------------------------ HTML -> 텍스트
const ENTITIES = {
  "&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
  "&#39;": "'", "&apos;": "'", "&ldquo;": '"', "&rdquo;": '"',
  "&lsquo;": "'", "&rsquo;": "'", "&middot;": "·", "&ndash;": "–",
  "&mdash;": "—", "&hellip;": "…", "&sim;": "~", "&deg;": "°",
};

function decodeEntities(text) {
  let out = text;
  for (const [k, v] of Object.entries(ENTITIES)) out = out.split(k).join(v);
  return out.replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)));
}

// 표는 한 행을 한 줄로, 칸은 ' | ' 로 잇는다.
// 등록금 반환 비율처럼 표로만 설명된 답이 있어서 그냥 버리면 답이 비어버린다.
function tablesToText(html) {
  return html.replace(/<table[\s\S]*?<\/table>/gi, (table) => {
    const rows = [...table.matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/gi)];
    const lines = rows.map((row) => {
      const cells = [...row[1].matchAll(/<t[hd][^>]*>([\s\S]*?)<\/t[hd]>/gi)];
      return cells.map((c) => stripTags(c[1]).replace(/\s+/g, " ").trim()).join(" | ");
    });
    return "\n" + lines.filter((l) => l.replace(/[|\s]/g, "")).join("\n") + "\n";
  });
}

function stripTags(html) {
  return html.replace(/<[^>]+>/g, " ");
}

function htmlToText(html) {
  let s = html;
  s = s.replace(/<script[\s\S]*?<\/script>/gi, "");
  s = s.replace(/<style[\s\S]*?<\/style>/gi, "");
  s = tablesToText(s);
  s = s.replace(/<br\s*\/?>/gi, "\n");
  s = s.replace(/<\/(p|div|li|tr|h[1-6])>/gi, "\n");
  s = s.replace(/<li[^>]*>/gi, "- ");
  s = stripTags(s);
  s = decodeEntities(s);
  // 줄 안의 공백만 접고 줄바꿈은 남긴다. 목록·표의 형태가 답의 일부다.
  s = s
    .split("\n")
    .map((line) => line.replace(/[ \t ]+/g, " ").trim())
    .filter((line) => line.length > 0)
    .join("\n");
  return s.trim();
}

// ------------------------------------------------------------ 파싱
function parsePage(html, page) {
  const start = html.indexOf("faq-wrapper");
  if (start < 0) throw new Error(`${page.label}: faq-wrapper 를 찾지 못했다`);
  const endMark = html.indexOf("paging-navigation", start);
  const zone = html.slice(start, endMark > 0 ? endMark : start + 300000);

  const declared = Number((html.match(/총\s*<strong>(\d+)<\/strong>\s*건/) || [])[1] || 0);
  const items = [];

  for (const dl of zone.matchAll(/<dl[^>]*>([\s\S]*?)<\/dl>/gi)) {
    const inner = dl[1];
    const q = inner.match(/<dt[^>]*>[\s\S]*?<strong[^>]*>([\s\S]*?)<\/strong>/i);
    const a = inner.match(/<dd[^>]*>([\s\S]*?)<\/dd>/i);
    if (!q || !a) continue;

    const question = htmlToText(q[1]).replace(/\s+/g, " ").trim();
    // 답변 안의 아이콘 이미지는 버린다.
    const answer = htmlToText(a[1].replace(/<img[^>]*>/gi, ""));
    if (!question || !answer) continue;

    items.push({ question, answer, section: page.label, source_url: url(page.code).split("?")[0] });
  }

  return { declared, items };
}

// ------------------------------------------------------------ 실행
async function main() {
  const all = [];
  const report = [];

  for (const page of PAGES) {
    const res = await fetch(url(page.code), { headers: { "User-Agent": "Mozilla/5.0" } });
    if (!res.ok) throw new Error(`${page.label}: HTTP ${res.status}`);
    const html = await res.text();

    const { declared, items } = parsePage(html, page);
    all.push(...items);
    report.push({ label: page.label, declared, parsed: items.length });
    console.log(
      `  ${page.label.padEnd(14)} 사이트표기 ${String(declared).padStart(3)}건  파싱 ${String(items.length).padStart(3)}건` +
        (declared === items.length ? "  일치" : "  !! 불일치")
    );
  }

  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(all, null, 2), "utf8");

  const mismatched = report.filter((r) => r.declared !== r.parsed);
  console.log(`\n총 ${all.length}건 -> ${path.relative(process.cwd(), OUT)}`);
  if (mismatched.length) {
    console.log("\n사이트가 표기한 건수와 파싱 건수가 다르다. 파서를 확인해야 한다:");
    mismatched.forEach((r) => console.log(`  ${r.label}: 표기 ${r.declared} vs 파싱 ${r.parsed}`));
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
