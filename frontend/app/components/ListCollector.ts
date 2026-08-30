// 목록 항목 모으기.
//
// 답변 본문은 LLM 이 만들기 때문에 항목 사이에 빈 줄이 들어올 때가 있다.
//
//   1. 셈틀꾼 동아리: ...
//   (빈 줄)
//   1. ACM 동아리: ...
//
// 빈 줄에서 목록을 끊으면 항목마다 <ol> 이 새로 시작해 번호가 전부 1 이 된다.
// 실제로 화면에 "1. 1. 1. 1." 로 나왔다.
//
// 그래서 빈 줄을 만나면 바로 끊지 않고 다음 내용을 먼저 본다.
// 같은 종류의 항목이 이어지면 하나의 목록으로 잇고, 아니면 거기서 끝낸다.
// (빈 줄 뒤에 문단이 오는 경우까지 목록으로 삼키면 안 된다.)
//
// 번호는 우리가 매기지 않는다. <ol> 이 알아서 1, 2, 3 으로 센다.
// LLM 이 "1." 만 반복해서 써 보내도 화면에는 제대로 나온다.

export type CollectResult = {
  items: string[];
  nextIndex: number;
};

export function collectListItems(
  lines: string[],
  startIndex: number,
  pattern: RegExp,
): CollectResult {
  const items: string[] = [];
  let index = startIndex;

  while (index < lines.length) {
    const match = lines[index].match(pattern);
    if (match) {
      items.push(match[1]);
      index += 1;
      continue;
    }

    if (lines[index].trim()) break;

    // 빈 줄이다. 다음 내용이 같은 목록인지 확인한다.
    let lookahead = index;
    while (lookahead < lines.length && !lines[lookahead].trim()) lookahead += 1;

    if (lookahead >= lines.length || !pattern.test(lines[lookahead])) break;

    index = lookahead;
  }

  return { items, nextIndex: index };
}
