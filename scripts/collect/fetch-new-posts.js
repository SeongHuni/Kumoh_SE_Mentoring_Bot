// se게시판에서 기준일 이후 새 글을 수집한다.
//
//   node scripts/collect/fetch-new-posts.js
//   SINCE=2026-07-21 node scripts/collect/fetch-new-posts.js
//
// seboard.site 는 공개 REST API를 제공한다(인증 불필요).
//   목록  GET /v1/posts?categoryId=1&page=N&perPage=50
//   상세  GET /v1/posts/{postId}   -> contents 에 본문 HTML
const fs = require("fs");
const path = require("path");

const BASE = "https://seboard.site";
const SINCE = process.env.SINCE || "2026-07-21"; // 기존 코퍼스의 최신 게시일
const OUT = path.join(process.cwd(), "outputs", "new_posts_raw.json");
const DELAY_MS = 300; // 서버 부담을 줄이려고 요청 사이에 쉰다

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function getJson(url, attempt = 1) {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    if (res.status >= 500 && attempt < 4) {
      await sleep(1000 * attempt);
      return getJson(url, attempt + 1);
    }
    throw new Error(`${res.status} ${url}`);
  }
  return res.json();
}

// 기준일 이후 글의 목록을 모은다. 목록이 최신순이므로 기준일 이전만 나오는 페이지에서 멈춘다.
async function listNewPosts() {
  const found = [];
  for (let page = 0; page < 20; page += 1) {
    const j = await getJson(`${BASE}/v1/posts?categoryId=1&page=${page}&perPage=50`);
    const items = j.content || [];
    if (!items.length) break;

    let sawNew = false;
    for (const p of items) {
      const day = String(p.createdAt).slice(0, 10);
      if (day > SINCE) {
        found.push(p);
        sawNew = true;
      }
    }
    if (!sawNew) break;
    await sleep(DELAY_MS);
  }
  return found;
}

async function main() {
  console.log(`기준일: ${SINCE} 이후 글을 수집합니다.`);
  const list = await listNewPosts();
  console.log(`목록에서 ${list.length}건 확인. 본문을 가져옵니다...`);

  const posts = [];
  for (const [i, p] of list.entries()) {
    const detail = await getJson(`${BASE}/v1/posts/${p.postId}`);
    posts.push({
      postId: detail.postId,
      title: detail.title,
      contents: detail.contents,
      boardCategory: detail.category?.name ?? null,
      author: detail.author?.name ?? null,
      createdAt: detail.createdAt,
      modifiedAt: detail.modifiedAt,
      views: detail.views,
      attachments: (detail.attachments || []).length,
    });
    process.stdout.write(`\r  ${i + 1}/${list.length}`);
    await sleep(DELAY_MS);
  }
  console.log();

  posts.sort((a, b) => a.postId - b.postId);
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(posts, null, 2), "utf8");

  console.log(`저장: ${path.relative(process.cwd(), OUT)} (${posts.length}건)`);
  const empty = posts.filter((p) => !p.contents || !p.contents.trim()).length;
  if (empty) console.log(`  주의: 본문이 빈 글 ${empty}건`);
}

main().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
