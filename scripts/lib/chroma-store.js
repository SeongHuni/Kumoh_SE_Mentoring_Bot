// Chroma 컬렉션 접근을 한 곳으로 모은다. 검색 호출부(ask.js, eval-chroma.js)가
// 컬렉션 이름·엔드포인트·필터 문법을 각자 알고 있지 않도록 하기 위한 얇은 래퍼다.
const { ChromaClient } = require("chromadb");

const COLLECTION = process.env.CHROMA_COLLECTION || "sw_notice_d500";
const CHROMA_URL = process.env.CHROMA_URL || "http://localhost:8000";

// ChromaClient는 'path' 대신 host/port/ssl을 받는다.
function connectionOptions() {
  const url = new URL(CHROMA_URL);
  return {
    host: url.hostname,
    port: Number(url.port || (url.protocol === "https:" ? 443 : 80)),
    ssl: url.protocol === "https:",
  };
}

// `docker compose up -d` 직후에는 서버가 아직 안 떠 있을 수 있다.
// 공식 이미지에 curl이 없어 compose healthcheck를 쓸 수 없으므로 호스트에서 기다린다.
async function waitForServer(client, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;

  while (Date.now() < deadline) {
    try {
      await client.heartbeat();
      return;
    } catch (error) {
      lastError = error;
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }

  throw new Error(
    `Chroma 서버에 ${timeoutMs / 1000}초 동안 연결하지 못했습니다 (${CHROMA_URL}). ` +
      `'npm run chroma'로 컨테이너를 띄웠는지 확인하세요. 원인: ${lastError && lastError.message}`
  );
}

async function openCollection() {
  const client = new ChromaClient(connectionOptions());
  await waitForServer(client);
  try {
    return await client.getCollection({ name: COLLECTION, embeddingFunction: null });
  } catch (error) {
    throw new Error(
      `컬렉션 '${COLLECTION}'을 열 수 없습니다 (${CHROMA_URL}). ` +
        `Chroma 서버가 떠 있는지, node scripts/load-chroma.js를 실행했는지 확인하세요. 원인: ${error.message}`
    );
  }
}

// filters: { category, source, year, since, until } -> Chroma where 절
// 조건이 2개 이상이면 $and로 묶어야 한다 (Chroma는 최상위 키 여러 개를 암묵적 AND로 처리하지 않는다).
// 값 하나면 $eq, 배열이면 $in. 검색 계획기가 "공식 공지"를 고르면
// se게시판과 학과공식사이트 두 곳을 함께 봐야 하므로 배열을 받는다.
function matchClause(field, value) {
  if (Array.isArray(value)) {
    const list = value.filter(Boolean);
    if (!list.length) return null;
    return list.length === 1 ? { [field]: { $eq: list[0] } } : { [field]: { $in: list } };
  }
  return { [field]: { $eq: value } };
}

function buildWhere(filters = {}) {
  const clauses = [];

  if (filters.category) clauses.push(matchClause("category", filters.category));
  if (filters.source) clauses.push(matchClause("source", filters.source));
  if (filters.year) clauses.push({ published_year: { $eq: Number(filters.year) } });
  if (filters.since) clauses.push({ published_ts: { $gte: toTs(filters.since) } });
  if (filters.until) clauses.push({ published_ts: { $lte: toTs(filters.until) } });

  const valid = clauses.filter(Boolean);
  if (!valid.length) return undefined;
  return valid.length === 1 ? valid[0] : { $and: valid };
}

function toTs(dateLike) {
  const match = String(dateLike).match(/^(\d{4})-?(\d{2})-?(\d{2})$/u);
  if (!match) throw new Error(`날짜 형식이 잘못됐습니다: ${dateLike} (YYYY-MM-DD 형태여야 합니다)`);
  return Number(`${match[1]}${match[2]}${match[3]}`);
}

async function search(collection, queryEmbedding, k = 5, filters = {}) {
  const result = await collection.query({
    queryEmbeddings: [queryEmbedding],
    nResults: k,
    where: buildWhere(filters),
    include: ["documents", "metadatas", "distances"],
  });

  return (result.ids[0] || []).map((id, i) => ({
    chunk_id: id,
    page_content: result.documents[0][i],
    metadata: result.metadatas[0][i] || {},
    // cosine 공간에서 Chroma가 돌려주는 distance는 1 - cosine similarity 다.
    score: 1 - result.distances[0][i],
  }));
}

module.exports = {
  COLLECTION,
  CHROMA_URL,
  connectionOptions,
  waitForServer,
  openCollection,
  buildWhere,
  search,
};
