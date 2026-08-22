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

  it("shows sources and recommendations for assistant messages", () => {
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
              index: 1,
              kind: "notice" as const,
              course: null,
              professor: null,
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
    expect(
      screen.getByRole("link", { name: "자료 1: 개설강좌 안내 원문 열기" }),
    ).toHaveAttribute("href", "https://example.com/source");
    expect(screen.getByText("[1]", { selector: ".source-index" })).toBeInTheDocument();
    expect(screen.queryByText("[자료 1]")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "수강신청 기간은?" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "다음 질문 추천" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "최근 공지" })).not.toBeInTheDocument();
  });

  it("renders Markdown headings, lists, emphasis, and ordinary links", () => {
    render(
      <ChatMessage
        message={{
          id: 3,
          role: "assistant",
          content:
            "## 신청 안내\n\n- **신청 기간**을 확인하세요. [1]\n- [통합정보시스템](https://example.com/system)에서 신청합니다.",
          sources: [
            {
              title: "신청 공지",
              url: "https://example.com/source",
              source: "kumoh",
              published_at: null,
              score: 0.9,
              index: 1,
              kind: "notice" as const,
              course: null,
              professor: null,
            },
          ],
          suggested_questions: [],
          recent_notices: [],
        }}
        isLoading={false}
        onSuggestion={vi.fn()}
      />,
    );

    expect(screen.getByRole("heading", { name: "신청 안내" })).toBeInTheDocument();
    expect(screen.getByText("신청 기간", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByRole("list")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "통합정보시스템" })).toHaveAttribute(
      "href",
      "https://example.com/system",
    );
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
    expect(screen.queryByRole("region", { name: "최근 공지" })).not.toBeInTheDocument();
  });

  it("does not render recent notices returned by the chat API", async () => {
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
        within(responseMessage as HTMLElement).queryByRole("region", { name: "최근 공지" }),
      ).not.toBeInTheDocument();
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
