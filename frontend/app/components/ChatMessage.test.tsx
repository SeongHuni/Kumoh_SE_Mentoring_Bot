import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import Home from "../page";
import { ChatMessage } from "./ChatMessage";

describe("ChatMessage", () => {
  it("renders each initial suggested question only once", () => {
    render(<Home />);

    expect(
      screen.getAllByRole("button", { name: "최근 수강신청 공지를 알려줘" }),
    ).toHaveLength(1);
  });

  it("shows sources, recommendations, and recent notices for assistant messages", () => {
    render(
      <ChatMessage
        message={{
          id: 1,
          role: "assistant",
          content: "개설강좌는 공지에서 확인할 수 있습니다. [자료 1]",
          sources: [
            {
              title: "개설강좌 안내",
              url: "https://example.com/source",
              source: "kumoh",
              published_at: "2026-03-20",
              score: 0.9,
            },
          ],
          grounded: true,
          suggested_questions: ["수강신청 기간은?"],
          recent_notices: [
            {
              title: "최근 개설강좌 공지",
              url: "https://example.com/recent",
              source: "kumoh",
              published_at: "2026-03-21",
              topic_key: "course_openings",
              topic_label: "개설강좌조회",
            },
          ],
        }}
        isLoading={false}
        onSuggestion={vi.fn()}
      />,
    );

    expect(screen.getByText("개설강좌 안내")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "수강신청 기간은?" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "다음 질문 추천" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "최근 공지" })).toBeInTheDocument();
    expect(
      screen.getByText("최근 공지", { selector: ".notice-heading" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /최근 개설강좌 공지/ })).toBeInTheDocument();
  });

  it("does not render assistant-only regions for user messages", () => {
    render(
      <ChatMessage
        message={{
          id: 2,
          role: "user",
          content: "개설강좌를 알려줘",
        }}
        isLoading={false}
        onSuggestion={vi.fn()}
      />,
    );

    expect(screen.getByText("개설강좌를 알려줘")).toBeInTheDocument();
    expect(screen.queryByText("참고한 게시글")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "다음 질문 추천" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "관련 최근 공지" })).not.toBeInTheDocument();
  });

  it("renders local answer sections with distinct visual hierarchy", () => {
    render(
      <ChatMessage
        message={{
          id: 3,
          role: "assistant",
          content: [
            "확인한 최신 공지",
            "",
            "1. 2026학년도 1학기 수강신청 안내",
            "분류 · 수업",
            "게시일 · 2026-02-11",
            "",
            "핵심 내용",
            "- 수강신청 전에 브라우저 캐시를 삭제하세요.",
            "출처 · [자료 1]",
            "",
            "원문 확인",
            "- 신청 가능 여부와 마감일은 원문에서 확인해 주세요.",
          ].join("\n"),
          sources: [],
          grounded: true,
          suggested_questions: [],
          recent_notices: [],
        }}
        isLoading={false}
        onSuggestion={vi.fn()}
      />,
    );

    expect(screen.getByText("확인한 최신 공지")).toHaveClass("answer-section-title");
    expect(screen.getByText("1. 2026학년도 1학기 수강신청 안내")).toHaveClass(
      "answer-notice-title",
    );
    expect(screen.getByText("분류 · 수업")).toHaveClass("answer-meta");
    expect(screen.getByText("게시일 · 2026-02-11")).toHaveClass("answer-meta");
    expect(screen.getByText("수강신청 전에 브라우저 캐시를 삭제하세요.")).toHaveClass(
      "answer-bullet",
    );
    expect(screen.getByText("출처 · [자료 1]")).toHaveClass("answer-citation");
  });

  it("renders recommendations and recent notices returned by the chat API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue({
          answer: "최근 개설강좌 공지를 확인해 주세요.",
          sources: [],
          grounded: true,
          suggested_questions: ["수강신청 기간은?"],
          recent_notices: [
            {
              title: "2026학년도 개설강좌 안내",
              url: "https://example.com/course",
              source: "kumoh",
              published_at: "2026-03-20",
              topic_key: "course_openings",
              topic_label: "개설강좌조회",
            },
          ],
        }),
      }),
    );
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      callback(0);
      return 0;
    });

    try {
      render(<Home />);

      fireEvent.change(screen.getByLabelText("질문 입력"), {
        target: { value: "개설강좌를 알려줘" },
      });
      fireEvent.click(screen.getByRole("button", { name: "질문 보내기" }));

      const answer = await screen.findByText("최근 개설강좌 공지를 확인해 주세요.");
      const responseMessage = answer.closest("article");

      expect(responseMessage).not.toBeNull();
      expect(
        within(responseMessage as HTMLElement).getByRole("region", {
          name: "다음 질문 추천",
        }),
      ).toBeInTheDocument();
      expect(
        within(responseMessage as HTMLElement).getByRole("region", {
          name: "최근 공지",
        }),
      ).toBeInTheDocument();
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
