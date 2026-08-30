import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MessageMarkdown } from "./MessageMarkdown";

const noSources: never[] = [];

describe("MessageMarkdown 목록", () => {
  it("항목 사이에 빈 줄이 있어도 하나의 번호 목록으로 잇는다", () => {
    // 답변은 LLM 이 만들기 때문에 항목 사이에 빈 줄이 들어올 때가 있다.
    // 빈 줄에서 끊으면 항목마다 <ol> 이 새로 시작해 번호가 전부 1 이 된다.
    // 실제로 화면에 "1. 1. 1." 로 나왔다.
    const content = [
      "비교과 프로그램으로는 다음과 같은 동아리가 있습니다:",
      "",
      "1. **셈틀꾼 동아리**: 프로그래밍 학술 동아리",
      "",
      "1. **ACM 동아리**: 프로그램 경진대회",
      "",
      "1. **BOSS 동아리**: 보안 분야 스터디",
    ].join("\n");

    const { container } = render(
      <MessageMarkdown content={content} sources={noSources} />,
    );

    const lists = container.querySelectorAll("ol");
    expect(lists).toHaveLength(1);
    expect(lists[0].querySelectorAll("li")).toHaveLength(3);
  });

  it("목록 뒤의 문단은 목록에 삼키지 않는다", () => {
    const content = [
      "1. 첫째 항목",
      "",
      "2. 둘째 항목",
      "",
      "이 외의 정보는 자료에서 확인할 수 없습니다.",
    ].join("\n");

    const { container } = render(
      <MessageMarkdown content={content} sources={noSources} />,
    );

    expect(container.querySelectorAll("ol li")).toHaveLength(2);
    expect(
      screen.getByText("이 외의 정보는 자료에서 확인할 수 없습니다."),
    ).toBeTruthy();
  });

  it("불릿 목록도 빈 줄을 건너뛰고 이어붙인다", () => {
    const content = ["- 첫째", "", "- 둘째", "", "- 셋째"].join("\n");

    const { container } = render(
      <MessageMarkdown content={content} sources={noSources} />,
    );

    expect(container.querySelectorAll("ul")).toHaveLength(1);
    expect(container.querySelectorAll("ul li")).toHaveLength(3);
  });

  it("빈 줄로 나뉜 서로 다른 종류의 목록은 합치지 않는다", () => {
    const content = ["1. 번호 항목", "", "- 불릿 항목"].join("\n");

    const { container } = render(
      <MessageMarkdown content={content} sources={noSources} />,
    );

    expect(container.querySelectorAll("ol")).toHaveLength(1);
    expect(container.querySelectorAll("ul")).toHaveLength(1);
  });

  it("붙어 있는 항목은 그대로 하나의 목록이다", () => {
    const content = ["1. 첫째", "2. 둘째", "3. 셋째"].join("\n");

    const { container } = render(
      <MessageMarkdown content={content} sources={noSources} />,
    );

    expect(container.querySelectorAll("ol")).toHaveLength(1);
    expect(container.querySelectorAll("ol li")).toHaveLength(3);
  });
});
