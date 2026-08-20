// D_500(500 tokens fixed-size, overlap 0) 청크와 이미 생성된 임베딩을 Chroma에 적재한다.
// 임베딩은 재계산하지 않고 embeddings.jsonl의 값을 그대로 넣으므로 API 비용이 들지 않는다.
const path = require("path");
const { ChromaClient } = require("chromadb");
const { EXPERIMENTS_DIR, loadExperimentRecords } = require("./lib/rag-core");

const { COLLECTION, CHROMA_URL, connectionOptions, waitForServer } = require("./lib/chroma-store");

const EXPERIMENT = process.env.RAG_EXPERIMENT || "D_500";
const BATCH_SIZE = Number(process.env.CHROMA_BATCH_SIZE || 100);

// Chroma 메타데이터 값은 string/number/boolean만 허용한다. null·undefined는 넣으면 거부되므로 제거한다.
function toChromaMetadata(meta) {
  const out = {};
  const copy = (key, value) => {
    if (value === null || value === undefined || value === "") return;
    out[key] = value;
  };

  copy("original_id", meta.original_id);
  copy("source", meta.source);
  copy("source_url", meta.sourceUrl);
  copy("title", meta.title);
  copy("author", meta.author);
  copy("category", meta.category);
  copy("published_at", meta.published_at);
  copy("crawled_at", meta.crawled_at);
  copy("chunk_index", meta.chunk_index);
  copy("chunk_count", meta.chunk_count);
  copy("estimated_tokens", meta.estimated_tokens);

  // Chroma의 범위 연산자($gte/$lte)는 숫자에만 안정적으로 동작한다.
  // "2026-07-21" 문자열로는 최신성 질문(특정 학기/연도)을 거를 수 없으므로
  // 정렬 가능한 정수 20260721 형태를 함께 저장한다.
  const ymd = String(meta.published_at || "").match(/^(\d{4})-(\d{2})-(\d{2})$/u);
  if (ymd) {
    out.published_ts = Number(`${ymd[1]}${ymd[2]}${ymd[3]}`);
    out.published_year = Number(ymd[1]);
  }

  return out;
}

async function main() {
  const client = new ChromaClient(connectionOptions());

  await waitForServer(client);
  console.log(`Chroma 연결됨 (${CHROMA_URL})`);

  // 재적재 시 이전 컬렉션이 남아 있으면 중복이 생기므로 지우고 새로 만든다.
  // listCollections()는 기존 컬렉션의 임베딩 함수를 복원하려다 경고를 뱉으므로 쓰지 않는다.
  try {
    await client.deleteCollection({ name: COLLECTION });
    console.log(`기존 컬렉션 삭제: ${COLLECTION}`);
  } catch {
    // 컬렉션이 없으면 그냥 넘어간다.
  }

  // 평가에서 쓴 지표와 맞추기 위해 cosine 공간으로 만든다 (Chroma 기본값은 l2).
  // embeddingFunction은 null로 둔다 — 임베딩을 항상 직접 넣으므로 Chroma가
  // 기본 임베딩 모델(@chroma-core/default-embed)을 찾다가 경고를 내는 것을 막는다.
  //
  // ef_search는 HNSW 탐색 폭이다. 기본값에서는 근사 오차 때문에 골든셋 80문항 중
  // 1문항 정도가 정확 검색과 다르게 나오고, 인덱스를 다시 만들 때마다 결과가 미세하게
  // 흔들린다(그래프 구성이 매번 달라지므로). 청크가 1,474개뿐이라 탐색 폭을 전체 규모까지
  // 키워도 지연 증가가 사실상 없으므로, 정확 검색과 일치하도록 크게 잡는다.
  const collection = await client.createCollection({
    name: COLLECTION,
    embeddingFunction: null,
    configuration: {
      hnsw: {
        space: "cosine",
        ef_search: Number(process.env.CHROMA_EF_SEARCH || 2000),
        ef_construction: Number(process.env.CHROMA_EF_CONSTRUCTION || 400),
        max_neighbors: Number(process.env.CHROMA_MAX_NEIGHBORS || 64),
      },
    },
    metadata: {
      experiment: EXPERIMENT,
      chunk_size_tokens: 500,
      chunk_overlap_tokens: 0,
      embedding_model: "text-embedding-3-small",
    },
  });

  const records = loadExperimentRecords(EXPERIMENT, EXPERIMENTS_DIR);
  console.log(`${EXPERIMENT}: ${records.length}개 청크 적재 시작 (batch=${BATCH_SIZE})`);

  for (let i = 0; i < records.length; i += BATCH_SIZE) {
    const batch = records.slice(i, i + BATCH_SIZE);
    await collection.add({
      ids: batch.map((r) => r.chunk_id),
      embeddings: batch.map((r) => r.embedding),
      documents: batch.map((r) => r.page_content),
      metadatas: batch.map((r) => toChromaMetadata(r.metadata)),
    });
    console.log(`  ${Math.min(i + BATCH_SIZE, records.length)}/${records.length}`);
  }

  const count = await collection.count();
  console.log(`적재 완료: 컬렉션 '${COLLECTION}'에 ${count}개 문서`);

  if (count !== records.length) {
    throw new Error(`적재 수 불일치: 기대 ${records.length}, 실제 ${count}`);
  }

  console.log(`\n다음: node scripts/ask.js "질문 내용"`);
  console.log(`데이터 경로: ${path.relative(process.cwd(), path.join(process.cwd(), "chroma-data"))}`);
}

main().catch((error) => {
  console.error(`적재 실패: ${error.message}`);
  process.exit(1);
});
