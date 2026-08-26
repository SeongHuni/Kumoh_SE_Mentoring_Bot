// data/*.json (에브리타임 강의평가 원본) -> 학과 게시판과 동일한 8칼럼 스키마로 변환
// 스키마: id, source, title, content, author, published_at, llm_category, crawled_at
// (document_type/url/metadata 없음 — 구조화 정보는 전부 content 문장으로 흡수,
//  요약/개별리뷰 구분은 id 접미사(_summary / _review_N)로만 구분)
// 실행: node scripts/convert_everytime_reviews.js
const fs = require("fs");
const path = require("path");

const DATA_DIR = path.join(__dirname, "..", "data");
const OUT_PATH = path.join(__dirname, "..", "converted", "everytime_documents.json");
const SOURCE_NAME = "에브리타임"; // 영문 그대로 쓰려면 "Everytime"으로 변경
const CRAWLED_AT = new Date().toISOString(); // 원본에 수집 시각이 없어 변환 시각으로 통일

const ASSIGNMENT_PHRASE = { 없음: "없는 편", 보통: "보통", 많음: "많은 편" };
const GROUP_PROJECT_PHRASE = { 없음: "없는 편", 보통: "보통 있는 편", 많음: "많은 편" };
const GRADING_PHRASE = { 너그러움: "너그러운 편", 보통: "보통", 깐깐함: "깐깐한 편" };

function pct(dist, key) {
  if (!dist || !(key in dist)) return null;
  return dist[key];
}

function sanitize(s) {
  return String(s).replace(/\s+/g, "");
}

function buildSummaryContent(course) {
  const { name, professor, average_rating, review_count, assignment, assignment_distribution,
    group_project, group_project_distribution, grading, grading_distribution, attendance, exam } = course;

  if (!review_count) {
    return `${name}(${professor} 교수) 과목은 아직 등록된 강의평이 없다.`;
  }

  const parts = [];
  parts.push(`${name}(${professor} 교수) 과목의 평균 평점은 5점 만점에 ${average_rating}점이며, 총 ${review_count}개의 강의평이 등록되어 있다.`);

  const aPct = pct(assignment_distribution, assignment);
  const aPhrase = ASSIGNMENT_PHRASE[assignment] || assignment;
  const gpPct = pct(group_project_distribution, group_project);
  const gpPhrase = GROUP_PROJECT_PHRASE[group_project] || group_project;
  const grPct = pct(grading_distribution, grading);
  const grPhrase = GRADING_PHRASE[grading] || grading;

  parts.push(
    `과제는 ${aPhrase}${aPct != null ? `(${aPct}%)` : ""}, ` +
    `조모임은 ${gpPhrase}${gpPct != null ? `(${gpPct}%)` : ""}, ` +
    `성적은 ${grPhrase}${grPct != null ? `(${grPct}%)` : ""}으로 평가된다.`
  );

  if (attendance || exam) {
    parts.push(`출결은 ${attendance || "정보 없음"} 방식이며, 시험은 ${exam || "정보 없음"} 실시한다.`);
  }

  return parts.join(" ");
}

const SEMESTER_START_MONTH = { "1학기": "03", "2학기": "09", 여름: "07", 겨울: "01" };

// 게시판 published_at 포맷("2026-07-21T15:37:53.676587")에 맞춤 — 정확한 시각은 없어 학기 시작일 00:00:00.000000으로 근사
function semesterToISODate(semester) {
  if (!semester) return null;
  const m = semester.match(/^(\d{2})년\s*(1학기|2학기|여름|겨울)$/);
  if (!m) return null;
  const year = 2000 + parseInt(m[1], 10);
  const month = SEMESTER_START_MONTH[m[2]];
  return `${year}-${month}-01T00:00:00.000000`;
}

function buildReviewContent(course, review, semester) {
  const facts = [`${semester || "학기 정보 없음"} 수강`, `평점 ${review.rating}/5`, `공감 ${review.likes ?? 0}개`];
  return `${course.name}(${course.professor} 교수) 수업 강의평 (${facts.join(", ")}): ${review.content}`;
}

function convertFile(filePath) {
  const raw = JSON.parse(fs.readFileSync(filePath, "utf-8"));
  const course = raw.course || {};
  const reviews = raw.reviews || [];
  const docs = [];

  const courseKey = `${sanitize(course.name)}_${sanitize(course.professor)}`;

  // 1) 과목 요약 문서 (파일당 1개)
  docs.push({
    id: `everytime_${courseKey}_summary`,
    source: SOURCE_NAME,
    title: `${course.name} (${course.professor}) 강의 요약`,
    content: buildSummaryContent(course),
    author: "익명",
    published_at: null,
    llm_category: "강의평",
    crawled_at: CRAWLED_AT,
  });

  // 2) 개별 리뷰 문서 (리뷰 개수만큼)
  for (const review of reviews) {
    const semester = review.semester ? review.semester.replace(/\s*수강자$/, "") : null;
    docs.push({
      id: `everytime_${review.id}`,
      source: SOURCE_NAME,
      title: `${course.name} (${course.professor}) 강의평`,
      content: buildReviewContent(course, review, semester),
      author: "익명",
      published_at: semesterToISODate(semester),
      llm_category: "강의평",
      crawled_at: CRAWLED_AT,
    });
  }

  return docs;
}

function main() {
  const files = fs.readdirSync(DATA_DIR).filter((f) => f.endsWith(".json"));
  let allDocs = [];
  let summaryCount = 0;
  let reviewCount = 0;

  for (const file of files) {
    const docs = convertFile(path.join(DATA_DIR, file));
    summaryCount += 1;
    reviewCount += docs.length - 1;
    allDocs = allDocs.concat(docs);
  }

  fs.mkdirSync(path.dirname(OUT_PATH), { recursive: true });
  fs.writeFileSync(OUT_PATH, JSON.stringify(allDocs, null, 2), "utf-8");

  console.log(`파일 수: ${files.length}`);
  console.log(`과목 요약 문서: ${summaryCount}`);
  console.log(`개별 리뷰 문서: ${reviewCount}`);
  console.log(`총 문서 수: ${allDocs.length}`);
  console.log(`출력: ${OUT_PATH}`);
}

main();
