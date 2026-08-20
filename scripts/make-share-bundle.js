// 동료에게 전달할 최소 배포 묶음을 만든다.
//   node scripts/make-share-bundle.js
//
// 적재가 끝난 Chroma 인덱스(chroma-data/)와 질의에 필요한 코드만 담는다.
// outputs/ 917MB나 임베딩 원본은 넣지 않는다 — 동료는 임베딩을 다시 만들 필요가 없다.
//
// API 키는 절대 넣지 않는다. 각자 자기 키를 쓴다.
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

const ROOT = process.cwd();
const BUNDLE_NAME = "sw-rag-share";
const OUT_DIR = path.join(ROOT, "dist");
const STAGE = path.join(OUT_DIR, BUNDLE_NAME);

// 묶음에 넣을 파일. 여기 없는 건 전달되지 않는다.
const FILES = [
  "docker-compose.yml",
  "scripts/ask.js",
  "scripts/lib/rag-core.js",
  "scripts/lib/chroma-store.js",
];

const PACKAGE_JSON = {
  name: "sw-rag-chatbot",
  version: "1.0.0",
  private: true,
  description: "소프트웨어전공 RAG 챗봇 (Chroma 인덱스 포함)",
  scripts: {
    chroma: "docker compose up -d",
    "chroma:stop": "docker compose down",
    "chroma:logs": "docker compose logs -f chroma",
    ask: "node scripts/ask.js",
  },
  dependencies: { chromadb: "^3.5.0" },
  engines: { node: ">=20" },
};

const SETUP_MD = `# 소프트웨어전공 RAG 챗봇 — 실행 안내

적재가 끝난 벡터 DB가 \`chroma-data/\`에 들어 있다. **임베딩을 다시 만들 필요가 없다.**

## 필요한 것

- Docker Desktop
- Node.js 20 이상
- 본인의 OpenAI API 키

## 실행

\`\`\`powershell
npm install
npm run chroma          # Chroma 컨테이너 기동 (docker compose up -d)
$env:OPENAI_API_KEY="sk-..."
node scripts/ask.js "장학금 신청 조건이 뭐야"
\`\`\`

키는 환경변수 대신 \`.secrets/embedding-api-key.txt\` 파일에 넣어도 된다.

## 질의 옵션

\`\`\`powershell
node scripts/ask.js "MT 갔었나" --year 2025
node scripts/ask.js "수강신청 일정" --since 2026-01-01 --category 수업 --k 8
node scripts/ask.js "자료구조 어때" --source 에브리타임
\`\`\`

| 옵션 | 설명 |
| --- | --- |
| \`--k\` | 검색할 청크 수 (기본 5) |
| \`--category\` | \`수업\`, \`장학금\`, \`행정·안내\`, \`학적·졸업\`, \`비교과·행사\`, \`취업·진로\`, \`연구·캡스톤\`, \`학생회\`, \`대학원\`, \`강의평\`, \`기타\` |
| \`--source\` | \`se게시판\`, \`에브리타임\`, \`학과공식사이트\` |
| \`--year\` | 작성 연도 |
| \`--since\` / \`--until\` | 작성일 범위 (\`YYYY-MM-DD\`) |

## 주의사항

**질문 임베딩 모델을 바꾸지 말 것.** 인덱스가 \`text-embedding-3-small\`로 만들어져 있다.
다른 모델로 질문을 임베딩하면 벡터 공간이 달라 검색 결과가 무의미해지는데,
**에러가 나지 않아서 알아채기 어렵다.** \`OPENAI_EMBEDDING_MODEL\` 환경변수를 건드리지 않으면 된다.

\`chroma-data/\`는 컨테이너에 볼륨으로 붙는다. 컨테이너를 지워도 데이터는 남는다.

## 포함된 데이터

- 문서 850건 → 청크 1,474개 (fixed-size 500 tokens, overlap 0)
- 출처: se게시판 1,253 / 에브리타임 202 / 학과공식사이트 19
- 임베딩 모델: \`text-embedding-3-small\` (1536차원), cosine

에브리타임 강의평이 포함되어 있다. **외부에 공개하지 말 것.**
`;

function copyFile(relPath) {
  const src = path.join(ROOT, relPath);
  const dest = path.join(STAGE, relPath);
  if (!fs.existsSync(src)) throw new Error(`필요한 파일이 없습니다: ${relPath}`);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.copyFileSync(src, dest);
}

// fs.cpSync는 이 디렉터리(44MB SQLite 포함)에서 Windows Node 22 기준 segfault를 낸다.
// 파일 단위 copyFileSync로 직접 순회한다.
function copyDir(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const from = path.join(src, entry.name);
    const to = path.join(dest, entry.name);
    if (entry.isDirectory()) copyDir(from, to);
    else fs.copyFileSync(from, to);
  }
}

// 컨테이너가 떠 있는 상태로 SQLite를 복사하면 쓰기 도중의 스냅샷을 뜨게 되어
// 동료가 받은 DB가 깨질 수 있다. 반드시 멈춘 뒤 복사한다.
async function assertChromaStopped() {
  const url = process.env.CHROMA_URL || "http://localhost:8000";
  try {
    const response = await fetch(`${url}/api/v2/heartbeat`, {
      signal: AbortSignal.timeout(2000),
    });
    if (response.ok) {
      throw new Error(
        `Chroma가 실행 중입니다 (${url}). 실행 중에 복사하면 DB가 깨진 상태로 전달될 수 있습니다.\n` +
          `먼저 'npm run chroma:stop'으로 멈춘 뒤 다시 실행하세요.`
      );
    }
  } catch (error) {
    // 연결 자체가 안 되면 정상 — 멈춰 있다는 뜻이다.
    if (error.message.includes("실행 중입니다")) throw error;
  }
}

function dirSizeMb(dir) {
  let total = 0;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    total += entry.isDirectory() ? dirSizeMb(full) * 1024 * 1024 : fs.statSync(full).size;
  }
  return total / 1024 / 1024;
}

async function main() {
  const chromaData = path.join(ROOT, "chroma-data");
  if (!fs.existsSync(chromaData)) {
    throw new Error("chroma-data/ 가 없습니다. 'npm run chroma' 후 'npm run load'를 먼저 실행하세요.");
  }

  await assertChromaStopped();

  fs.rmSync(STAGE, { recursive: true, force: true });
  fs.mkdirSync(STAGE, { recursive: true });

  for (const file of FILES) copyFile(file);

  fs.writeFileSync(path.join(STAGE, "package.json"), JSON.stringify(PACKAGE_JSON, null, 2) + "\n", "utf8");
  fs.writeFileSync(path.join(STAGE, "SETUP.md"), SETUP_MD, "utf8");

  // 적재된 인덱스를 통째로 복사한다. 이게 묶음 용량의 대부분이다.
  copyDir(chromaData, path.join(STAGE, "chroma-data"));

  // 키가 섞여 들어가지 않았는지 확인한다. 실수로 포함되면 배포 사고다.
  const leaked = [];
  const scan = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "chroma-data") continue;
        scan(full);
      } else if (/sk-[A-Za-z0-9_-]{20,}/u.test(fs.readFileSync(full, "utf8"))) {
        leaked.push(path.relative(STAGE, full));
      }
    }
  };
  scan(STAGE);
  if (leaked.length) {
    throw new Error(`API 키로 보이는 문자열이 묶음에 들어 있습니다: ${leaked.join(", ")}`);
  }

  const sizeMb = dirSizeMb(STAGE);
  console.log(`묶음 생성: ${path.relative(ROOT, STAGE)} (${sizeMb.toFixed(1)} MB)`);

  // Windows 기본 tar로 zip을 만든다. 별도 도구가 필요 없다.
  const zipPath = path.join(OUT_DIR, `${BUNDLE_NAME}.zip`);
  fs.rmSync(zipPath, { force: true });
  execFileSync("tar", ["-a", "-c", "-f", zipPath, "-C", OUT_DIR, BUNDLE_NAME], { stdio: "inherit" });

  const zipMb = fs.statSync(zipPath).size / 1024 / 1024;
  console.log(`압축 완료: ${path.relative(ROOT, zipPath)} (${zipMb.toFixed(1)} MB)`);
  console.log(`\n동료에게 이 zip 하나만 전달하면 된다. 압축을 풀고 SETUP.md를 따르면 실행된다.`);
  console.log(`API 키는 포함되지 않았다 — 각자 본인 키를 사용한다.`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
