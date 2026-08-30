import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MessageMarkdown } from "./MessageMarkdown";

const noSources: never[] = [];
const NL = "\n";

describe("MessageMarkdown 목록", () => {
  it("항목 사이에 빈 줄이 있어도 하나의 번호 목록으로 잇는다", () => {
    // 답변은 LLM 이 만들기 때문에 항목 사이에 빈 줄이 들어올 때가 있다.
    // 빈 줄에서 끊으면 항목마다 <ol> 이 새로 시작해 번호가 전부 1 이 된다.
    const content = [
      "비교과 프로그램으로는 다음과 같은 동아리가 있습니다:",
      "",
      "1. **셈틀꾼 동아리**: 프로그래밍 학술 동아리",
      "",
      "1. **ACM 동아리**: 프로그램 경진대회",
      "",
      "1. **BOSS 동아리**: 보안 분야 스터디",
    ].join(NL);

    const { container } = render(
      <MessageMarkdown content={content} sources={noSources} />,
    );

    const lists = container.querySelectorAll("ol");
    expect(lists).toHaveLength(1);
    expect(lists[0].querySelectorAll("li")).toHaveLength(3);
  });

  it("불릿 상세가 끼어 있어도 번호가 이어진다", () => {
    // 실제 화면에서 나온 형태. 항목의 상세 내용이 들여쓰기 없는 불릿으로
    // 따라오는데, 그게 번호 목록을 끊어서 "1. 1." 로 나왔다.
    const content = [
      "채용설명회에 대한 정보는 다음과 같습니다:",
      "",
      "1. (주)세원물산 채용설명회",
      "",
      "- **일시**: 2026년 6월 18일(목) 15:00~16:00",
      "- **장소**: 디지털관 시청각실",
      "",
      "1. 다쏘시스템 채용설명회",
      "",
      "- **일시**: 2025년 3월 19일(수) 12:30~13:30",
      "- **장소**: 디지털관 시청각실(DB127)",
      "",
      "이 외의 채용설명회에 대한 정보는 확인할 수 없습니다.",
    ].join(NL);

    const { container } = render(
      <MessageMarkdown content={content} sources={noSources} />,
    );

    const lists = container.querySelectorAll("ol");
    expect(lists).toHaveLength(1);

    const topLevel = lists[0].querySelectorAll(":scope > li");
    expect(topLevel).toHaveLength(2);

    // 상세는 각 항목의 하위 목록으로 들어간다
    expect(topLevel[0].querySelectorAll("ul li")).toHaveLength(2);
    expect(topLevel[1].querySelectorAll("ul li")).toHaveLength(2);

    // 뒤의 문단은 목록에 삼키지 않는다
    expect(
      screen.getByText("이 외의 채용설명회에 대한 정보는 확인할 수 없습니다."),
    ).toBeTruthy();
  });

  it("목록 뒤의 문단은 목록에 삼키지 않는다", () => {
    const content = [
      "1. 첫째 항목",
      "",
      "2. 둘째 항목",
      "",
      "이 외의 정보는 자료에서 확인할 수 없습니다.",
    ].join(NL);

    const { container } = render(
      <MessageMarkdown content={content} sources={noSources} />,
    );

    expect(container.querySelectorAll("ol > li")).toHaveLength(2);
    expect(
      screen.getByText("이 외의 정보는 자료에서 확인할 수 없습니다."),
    ).toBeTruthy();
  });

  it("불릿 목록도 빈 줄을 건너뛰고 이어붙인다", () => {
    const content = ["- 첫째", "", "- 둘째", "", "- 셋째"].join(NL);

    const { container } = render(
      <MessageMarkdown content={content} sources={noSources} />,
    );

    expect(container.querySelectorAll("ul")).toHaveLength(1);
    expect(container.querySelectorAll("ul li")).toHaveLength(3);
  });

  it("번호 항목 없이 시작한 불릿은 그대로 독립 목록이다", () => {
    const content = ["- 첫째", "- 둘째"].join(NL);

    const { container } = render(
      <MessageMarkdown content={content} sources={noSources} />,
    );

    expect(container.querySelectorAll("ol")).toHaveLength(0);
    expect(container.querySelectorAll("ul li")).toHaveLength(2);
  });

  it("붙어 있는 항목은 그대로 하나의 목록이다", () => {
    const content = ["1. 첫째", "2. 둘째", "3. 셋째"].join(NL);

    const { container } = render(
      <MessageMarkdown content={content} sources={noSources} />,
    );

    expect(container.querySelectorAll("ol")).toHaveLength(1);
    expect(container.querySelectorAll("ol > li")).toHaveLength(3);
  });
});
