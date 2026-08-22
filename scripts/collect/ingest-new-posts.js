// 새 글을 코퍼스에 병합하고 청킹·임베딩해 Chroma에 증분 추가한다.
//
//   node scripts/collect/ingest-new-posts.js            실제 반영
//   node scripts/collect/ingest-new-posts.js --dry-run  무엇이 바뀌는지만 확인
//
// 기존 1,474청크는 그대로 두고 새 청크만 얹는다. 전체 재적재가 아니므로
// 임베딩 비용도 신규분만 든다.
//
// 청킹은 D_500 과 동일해야 한다(500 tokens, overlap 0, 헤더 부착).
// create-chunks.js 의 분할 규칙을 그대로 쓴다.
const fs = require("fs");
const path = require("path");
const { ChromaClient } = require("chromadb");

const {
  estimateTokenCount,
  hardSplitByTokenEstimate,
  stripExistingHeader,
  buildHeader,
} = require("../lib/chunking-common");
const { readApiKey, embedBatch, readJsonl } = require("../lib/rag-core");
const { COLLECTION, CHROMA_URL, connectionOptions, waitForServer } = require("../lib/chroma-store");

const ROOT = process.cwd();
const CORPUS = path.join(ROOT, "data", "document통합파일(에타리뷰분리).json");
const NEW_DOCS = path.join(ROOT, "outputs", "new_posts_converted.json");
const EXP_DIR = path.join(ROOT, "outputs", "chunking_experiments", "D_500");
const CHUNK_SIZE = 500;
const DRY = process.argv.includes("--dry-run");

// --- create-chunks.js 의 splitNatural / splitByEstimatedTokens 와 동일한 규칙 ---
function splitNatural(text) {
  const normalized = String(text || "").replace(/\r\n/g, "\n").trim();
  if (!normalized) return [];
  const chunks = [];
  for (const paragraph of normalized.split(/\n{2,}/u).map((p) => p.trim()).filter(Boolean)) {
    for (const listPart of paragraph
      .split(/\n(?=\s*(?:[-*•◦]|\d+[.)]|[가-하][.)]))/u)
      .map((p) => p.trim())
      .filter(Boolean)) {
      const sentences = listPart
        .replace(/([.!?。！？]|(?:다|요|니다|음|함)\.)\s+/gu, "$1\n")
        .split(/\n+/u)
        .map((p) => p.trim())
        .filter(Boolean);
      chunks.push(...sentences);
    }
  }
  return chunks.length ? chunks : [normalized];
}

function splitByEstimatedTokens(body, maxTokens) {
  const segments = splitNatural(body);
  const chunks = [];
  let current = "";
  let currentTokens = 0;

  for (const segment of segments) {
    const segmentTokens = estimateTokenCount(segment);
    if (segmentTokens > maxTokens) {
      if (current.trim()) { chunks.push(current.trim()); current = ""; currentTokens = 0; }
      chunks.push(...hardSplitByTokenEstimate(segment, maxTokens));
      continue;
    }
    if (current && currentTokens + segmentTokens > maxTokens) {
      chunks.push(current.trim());
      current = segment;
      currentTokens = segmentTokens;
    } else {
      current = current ? `${current}\n${segment}` : segment;
      currentTokens += segmentTokens;
    }
  }
  if (current.trim()) chunks.push(current.trim());
  return chunks;
}

function makeChunks(doc) {
  const metadata = doc.metadata || {};
  const originalId = metadata.id;
  const header = buildHeader(metadata);
  const body = stripExistingHeader(doc.page_content);
  const bodyChunks = splitByEstimatedTokens(body, CHUNK_SIZE);

  return bodyChunks.map((bodyChunk, index) => {
    const content = header ? `${header}\n\n${bodyChunk}`.trim() : bodyChunk.trim();
    return {
      page_content: content,
      metadata: {
        ...metadata,
        original_id: originalId,
        chunk_id: `${originalId}::D_500::${String(index).padStart(4, "0")}`,
        chunk_index: index,
        chunk_count: bodyChunks.length,
        experiment: "D_500",
        experiment_label: "D",
        chunk_size_tokens: CHUNK_SIZE,
        chunk_overlap_tokens: 0,
        token_count_method: "estimated_local_no_tiktoken",
        estimated_tokens: estimateTokenCount(content),
      },
    };
  });
}

// load-chroma.js 의 toChromaMetadata 와 동일해야 필터가 같게 동작한다.
function toChromaMetadata(meta) {
  const out = {};
  const copy = (k, v) => { if (v !== null && v !== undefined && v !== "") out[k] = v; };
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
  const ymd = String(meta.published_at || "").match(/^(\d{4})-(\d{2})-(\d{2})$/u);
  if (ymd) {
    out.published_ts = Number(`${ymd[1]}${ymd[2]}${ymd[3]}`);
    out.published_year = Number(ymd[1]);
  }
  return out;
}

async function main() {
  const corpus = JSON.parse(fs.readFileSync(CORPUS, "utf8"));
  const newDocs = JSON.parse(fs.readFileSync(NEW_DOCS, "utf8"));
  const existingIds = new Set(corpus.map((d) => d.metadata.id));

  const toAdd = newDocs.filter((d) => !existingIds.has(d.metadata.id));
  console.log(`새 문서 ${toAdd.length}건 (전체 ${newDocs.length}건 중 중복 ${newDocs.length - toAdd.length}건 제외)`);
  if (!toAdd.length) { console.log("추가할 것이 없습니다."); return; }

  const newChunks = toAdd.flatMap(makeChunks);
  const tokens = newChunks.reduce((s, c) => s + c.metadata.estimated_tokens, 0);
  console.log(`새 청크 ${newChunks.length}개 · 약 ${tokens.toLocaleString()} 토큰`);
  console.log(`임베딩 예상 비용: $${(tokens / 1e6 * 0.02).toFixed(4)}`);

  // 이미 적재된 chunk_id 와 겹치지 않는지 확인 (증분 추가의 안전장치)
  const existingChunkIds = new Set(
    readJsonl(path.join(EXP_DIR, "chunks.jsonl")).map((c) => c.metadata.chunk_id)
  );
  const collide = newChunks.filter((c) => existingChunkIds.has(c.metadata.chunk_id));
  if (collide.length) throw new Error(`chunk_id 충돌 ${collide.length}건: ${collide[0].metadata.chunk_id}`);

  if (DRY) {
    console.log("\n--dry-run 이므로 여기서 멈춥니다. 추가될 청크 미리보기:");
    newChunks.slice(0, 3).forEach((c) => {
      console.log(`  ${c.metadata.chunk_id}  (${c.metadata.estimated_tokens} tok)`);
      console.log(`    ${c.page_content.replace(/\n/g, " ").slice(0, 90)}...`);
    });
    return;
  }

  // 1) 임베딩
  const apiKey = readApiKey();
  console.log("\n임베딩 생성 중...");
  const embeddings = [];
  for (let i = 0; i < newChunks.length; i += 64) {
    const batch = newChunks.slice(i, i + 64);
    embeddings.push(...(await embedBatch(apiKey, batch.map((c) => c.page_content))));
    process.stdout.write(`\r  ${Math.min(i + 64, newChunks.length)}/${newChunks.length}`);
  }
  console.log();

  // 2) Chroma 증분 추가
  const client = new ChromaClient(connectionOptions());
  await waitForServer(client);
  const collection = await client.getCollection({ name: COLLECTION, embeddingFunction: null });
  const before = await collection.count();

  await collection.add({
    ids: newChunks.map((c) => c.metadata.chunk_id),
    embeddings,
    documents: newChunks.map((c) => c.page_content),
    metadatas: newChunks.map((c) => toChromaMetadata(c.metadata)),
  });
  const after = await collection.count();
  console.log(`Chroma: ${before} -> ${after} 청크 (+${after - before})`);

  // 3) 원본 파일들도 갱신해 재적재 시 복구되도록 한다
  fs.writeFileSync(CORPUS, JSON.stringify([...corpus, ...toAdd], null, 2), "utf8");
  fs.appendFileSync(
    path.join(EXP_DIR, "chunks.jsonl"),
    newChunks.map((c) => JSON.stringify(c)).join("\n") + "\n",
    "utf8"
  );
  fs.appendFileSync(
    path.join(EXP_DIR, "embeddings.jsonl"),
    newChunks
      .map((c, i) => JSON.stringify({
        chunk_id: c.metadata.chunk_id,
        original_id: c.metadata.original_id,
        experiment: "D_500",
        model: "text-embedding-3-small",
        embedding: embeddings[i],
        metadata: c.metadata,
      }))
      .join("\n") + "\n",
    "utf8"
  );

  console.log(`코퍼스: ${corpus.length} -> ${corpus.length + toAdd.length} 문서`);
  console.log(`\n완료. 확인: node scripts/chat.js "MT 수요조사 어떻게 해"`);
}

main().catch((e) => { console.error(e.message); process.exit(1); });
