import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChatMessage } from "./ChatMessage";

describe("ChatMessage", () => {
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
    expect(screen.getByText("최근 공지", { selector: ".notice-heading" })).toBeInTheDocument();
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
    expect(screen.queryByRole("region", { name: "최근 공지" })).not.toBeInTheDocument();
  });
});
