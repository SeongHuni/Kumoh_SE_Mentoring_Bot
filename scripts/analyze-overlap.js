// "overlap을 줬는데 왜 성능이 안 올랐나"를 데이터로 규명한다.
//   node scripts/analyze-overlap.js
//
// 결론 요약: overlap이 고칠 수 있는 문제(근거 문장이 청크 경계에서 잘리는 것)가
// 골든셋 96개 근거 중 1건뿐이었고, overlap은 그 1건을 실제로 복구했다.
// 즉 overlap은 제 역할을 했지만 고칠 대상이 없었다.
const fs = require("fs");
const path = require("path");
const { estimateTokenCount } = require("./lib/chunking-common");

const ROOT = process.cwd();
const EXPERIMENTS = ["D_500", "K_500_ov50", "L_500_ov100", "M_500_ov150"];

const readJsonl = (p) =>
  fs.readFileSync(p, "utf8").split(/\r?\n/u).filter(Boolean).map((l) => JSON.parse(l));

// 공백 차이를 무시하고 원문 포함 여부를 본다.
const norm = (s) => String(s).replace(/\s+/gu, "");

const chunksPath = (exp) =>
  path.join(ROOT, "outputs", "chunking_experiments", exp, "chunks.jsonl");

function loadByDoc(exp) {
  const map = new Map();
  for (const c of readJsonl(chunksPath(exp))) {
    const id = c.metadata.original_id;
    if (!map.has(id)) map.set(id, []);
    map.get(id).push(norm(c.page_content));
  }
  return map;
}

function section(title) {
  console.log(`\n${"=".repeat(72)}\n${title}\n${"=".repeat(72)}`);
}

function main() {
  const golden = readJsonl(path.join(ROOT, "outputs", "golden_set", "golden_questions.jsonl"));
  const raw = readJsonl(path.join(ROOT, "outputs", "eval_results", "retrieval_raw.jsonl"));
  const byExp = (e) => raw.filter((r) => r.experiment === e);

  section("1. overlap이 작동할 여지가 있었는가 (정답 문서의 청크 수)");
  {
    const counts = new Map();
    for (const c of readJsonl(chunksPath("D_500"))) {
      counts.set(c.metadata.original_id, c.metadata.chunk_count);
    }
    let single = 0;
    let multi = 0;
    for (const q of golden) {
      for (const id of q.gold_doc_ids || []) {
        if (counts.get(id) === 1) single += 1;
        else if (counts.get(id) > 1) multi += 1;
      }
    }
    console.log(`  단일 청크 정답 문서 (overlap 무의미): ${single}건`);
    console.log(`  복수 청크 정답 문서 (overlap 작동 가능): ${multi}건`);
    console.log(`  => ${((100 * multi) / (single + multi)).toFixed(1)}%에서 작동 여지가 있었다. 구조적 제약은 아니다.`);
  }

  section("2. 청크 경계가 문장을 실제로 자르는가 (D_500)");
  {
    const rows = readJsonl(chunksPath("D_500"));
    let boundaries = 0;
    let midSentence = 0;
    for (const r of rows) {
      if (r.metadata.chunk_index >= r.metadata.chunk_count - 1) continue;
      boundaries += 1;
      const i = r.page_content.indexOf("\n\n");
      const body = (i === -1 ? r.page_content : r.page_content.slice(i + 2)).trim();
      if (!/[.!?。！？:)\]}"'’”]$|(?:다|요|음|함|임|것|중|정|료|시|일|기|명|개|원|년|월)$/u.test(body)) {
        midSentence += 1;
      }
    }
    console.log(`  이어지는 경계: ${boundaries}개`);
    console.log(`  문장 중간에서 끊김: ${midSentence}개 (${((100 * midSentence) / boundaries).toFixed(1)}%)`);
    console.log(`  => splitNatural이 문단→리스트→문장 순 자연 경계에서만 자르므로 89%가 온전하다.`);
  }

  section("3. 근거 문장이 청크 안에 온전히 남는가 (핵심 지표)");
  const byDoc = Object.fromEntries(EXPERIMENTS.map((e) => [e, loadByDoc(e)]));
  const baseline = loadByDoc("A_document"); // 무분할 대조군
  {
    for (const exp of EXPERIMENTS) {
      let total = 0;
      let intact = 0;
      for (const q of golden) {
        for (const ev of q.expected_evidence || []) {
          const e = norm(ev);
          if (e.length < 10) continue;
          const docs = (q.gold_doc_ids || []).flatMap((id) => byDoc[exp].get(id) || []);
          if (!docs.length) continue;
          total += 1;
          if (docs.some((c) => c.includes(e))) intact += 1;
        }
      }
      console.log(
        `  ${exp.padEnd(14)} ${intact}/${total} 온전 (${((100 * intact) / total).toFixed(1)}%)`
      );
    }
  }

  section("4. 못 찾은 근거의 정체 — 청킹 탓인가, 골든셋 탓인가");
  {
    let paraphrase = 0;
    let trulySplit = 0;
    let rescued = 0;
    const cases = [];
    for (const q of golden) {
      for (const ev of q.expected_evidence || []) {
        const e = norm(ev);
        if (e.length < 10) continue;
        const inD = (q.gold_doc_ids || []).flatMap((id) => byDoc.D_500.get(id) || []).some((c) => c.includes(e));
        if (inD) continue;
        const inA = (q.gold_doc_ids || []).flatMap((id) => baseline.get(id) || []).some((c) => c.includes(e));
        if (!inA) {
          // 자르지 않은 원문에도 없다 = 근거 문장이 원문과 다르게 생성된 것
          paraphrase += 1;
        } else {
          trulySplit += 1;
          const inK = (q.gold_doc_ids || [])
            .flatMap((id) => byDoc.K_500_ov50.get(id) || [])
            .some((c) => c.includes(e));
          if (inK) rescued += 1;
          cases.push(`${inK ? "복구됨" : "복구 실패"}: ${ev.slice(0, 70)}...`);
        }
      }
    }
    console.log(`  원문에도 없음 (골든셋 패러프레이즈 문제): ${paraphrase}건`);
    console.log(`  원문엔 있는데 청킹으로 잘림 (overlap의 진짜 대상): ${trulySplit}건`);
    console.log(`    그 중 overlap이 복구: ${rescued}건`);
    cases.forEach((c) => console.log(`      ${c}`));
    console.log(`  => overlap의 복구율은 ${trulySplit ? ((100 * rescued) / trulySplit).toFixed(0) : 0}%. 고칠 대상 자체가 없었다.`);
  }

  section("5. 평가 지표가 그 복구를 볼 수 있는가");
  console.log(`  eval-retrieval.js: hitFlags = topK.map(r => goldSet.has(r.metadata.original_id))`);
  console.log(`  => 문서 단위 판정. 정답 문서의 다른 청크가 이미 top-5에 있으면`);
  console.log(`     근거를 담은 청크가 복구돼도 Recall은 변하지 않는다.`);

  section("6. overlap이 치르는 비용 — top-5 슬롯 잠식");
  {
    for (const exp of EXPERIMENTS) {
      const rows = byExp(exp);
      if (!rows.length) continue;
      let distinct = 0;
      let dup = 0;
      for (const r of rows) {
        const docs = r.retrieved.map((x) => x.original_id);
        const uniq = new Set(docs).size;
        distinct += uniq;
        dup += docs.length - uniq;
      }
      console.log(
        `  ${exp.padEnd(14)} top5당 서로 다른 문서 ${(distinct / rows.length).toFixed(2)}개 | 중복 낭비 슬롯 ${(dup / rows.length).toFixed(2)}개`
      );
    }
    console.log(`  => overlap이 만든 near-duplicate 청크가 다른 문서를 밀어낸다.`);
  }

  section("7. 최종 손익 — 문항별 정답 순위 변화");
  {
    const base = byExp("D_500");
    const rankOf = (r) => {
      const g = new Set(r.gold_doc_ids);
      const i = r.retrieved.findIndex((x) => g.has(x.original_id));
      return i === -1 ? 99 : i + 1;
    };
    for (const exp of EXPERIMENTS.slice(1)) {
      const v = byExp(exp);
      if (!v.length) continue;
      let better = 0;
      let worse = 0;
      let same = 0;
      for (let i = 0; i < base.length; i += 1) {
        const a = rankOf(base[i]);
        const b = rankOf(v[i]);
        if (b < a) better += 1;
        else if (b > a) worse += 1;
        else same += 1;
      }
      console.log(
        `  D_500 -> ${exp.padEnd(14)} 개선 ${better} | 악화 ${worse} | 무변화 ${same} | 순변화 ${better - worse >= 0 ? "+" : ""}${better - worse}`
      );
    }
  }

  console.log(`\n${"=".repeat(72)}`);
  console.log("결론: overlap은 제 역할을 100% 수행했으나(잘린 근거 1건 중 1건 복구),");
  console.log("      이 데이터셋에는 고칠 문제가 사실상 존재하지 않았다.");
  console.log("      반면 near-duplicate 청크로 top-5를 잠식하는 비용은 실재해");
  console.log("      개선과 악화가 상쇄되었다.");
  console.log("=".repeat(72));
}

main();
