// 목록 항목 모으기.
//
// 답변 본문은 LLM 이 만들기 때문에 목록 모양이 두 가지로 흐트러진다.
//
// (1) 항목 사이에 빈 줄이 들어온다
//
//       1. 셈틀꾼 동아리: ...
//       (빈 줄)
//       1. ACM 동아리: ...
//
// (2) 항목의 상세 내용이 불릿으로 따라오는데 들여쓰기가 없다
//
//       1. (주)세원물산 채용설명회
//       (빈 줄)
//       - 일시: 2026년 6월 18일
//       - 장소: 디지털관 시청각실
//       (빈 줄)
//       1. 다쏘시스템 채용설명회
//
// 둘 다 거기서 목록을 끊으면 항목마다 <ol> 이 새로 시작해 번호가 전부 1 이 된다.
// 실제로 화면에 "1. 1." 로 나왔다.
//
// 그래서 빈 줄과 불릿을 만나도 바로 끊지 않는다.
// 빈 줄은 건너뛰고 다음 내용을 보고, 불릿은 직전 번호 항목의 하위 내용으로 붙인다.
// 빈 줄 뒤에 문단이 오는 경우까지 삼키면 안 되므로 거기서는 끝낸다.
//
// 번호는 우리가 매기지 않는다. <ol> 이 알아서 1, 2, 3 으로 센다.
// LLM 이 "1." 만 반복해서 써 보내도 화면에는 제대로 나온다.

// 들여쓰기를 허용한다. 실제 답변은 두 형태가 다 온다.
//
//   1. (주)세원물산 채용설명회
//      - 일시: ...        <- 3칸 들여쓴 불릿
//
//   1. 셈틀꾼 동아리
//   - 일시: ...           <- 들여쓰기 없는 불릿
//
// 앞에 공백이 있다고 목록이 아니라고 보면 거기서 끊겨 번호가 다시 1 이 된다.
export const UNORDERED_ITEM = /^\s*[-*+]\s+(.+)$/;
export const ORDERED_ITEM = /^\s*\d+[.)]\s+(.+)$/;

export type OrderedItem = {
  text: string;
  /** 들여쓰기 없이 따라온 불릿. 이 항목의 하위 목록으로 렌더한다. */
  children: string[];
};

export type CollectResult<T> = {
  items: T[];
  nextIndex: number;
};

/** 빈 줄이 몇 개든 건너뛴 다음 줄의 위치. 끝까지 비어 있으면 lines.length. */
function skipBlank(lines: string[], from: number): number {
  let index = from;
  while (index < lines.length && !lines[index].trim()) index += 1;
  return index;
}

/** 불릿 목록. 빈 줄은 건너뛰고, 다음 내용이 불릿일 때만 잇는다. */
export function collectUnorderedItems(
  lines: string[],
  startIndex: number,
): CollectResult<string> {
  const items: string[] = [];
  let index = startIndex;

  while (index < lines.length) {
    const match = lines[index].match(UNORDERED_ITEM);
    if (match) {
      items.push(match[1]);
      index += 1;
      continue;
    }

    if (lines[index].trim()) break;

    const next = skipBlank(lines, index);
    if (next >= lines.length || !UNORDERED_ITEM.test(lines[next])) break;
    index = next;
  }

  return { items, nextIndex: index };
}

/** 번호 목록. 빈 줄을 건너뛰고, 들여쓰기 없는 불릿은 직전 항목의 하위로 붙인다. */
export function collectOrderedItems(
  lines: string[],
  startIndex: number,
): CollectResult<OrderedItem> {
  const items: OrderedItem[] = [];
  let index = startIndex;

  while (index < lines.length) {
    const ordered = lines[index].match(ORDERED_ITEM);
    if (ordered) {
      items.push({ text: ordered[1], children: [] });
      index += 1;
      continue;
    }

    // 번호 항목이 하나라도 나온 뒤의 불릿은 그 항목의 상세 내용으로 본다.
    const bullet = items.length ? lines[index].match(UNORDERED_ITEM) : null;
    if (bullet) {
      items[items.length - 1].children.push(bullet[1]);
      index += 1;
      continue;
    }

    if (lines[index].trim()) break;

    const next = skipBlank(lines, index);
    if (next >= lines.length) break;

    const continues =
      ORDERED_ITEM.test(lines[next]) ||
      (items.length > 0 && UNORDERED_ITEM.test(lines[next]));
    if (!continues) break;

    index = next;
  }

  return { items, nextIndex: index };
}
