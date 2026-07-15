import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ChatReply } from "./lib/chatApi";
import { requestChat } from "./lib/chatApi";
import Home from "./page";

vi.mock("./lib/chatApi", () => ({
  requestChat: vi.fn(),
}));

const mockedRequestChat = vi.mocked(requestChat);

const reply: ChatReply = {
  content: "수강신청은 포털에서 진행합니다.",
  sources: [
    {
      title: "수강신청 안내",
      url: "https://example.test/course",
      source: "kumoh",
      published_at: "2026-07-15",
      score: 0.98,
    },
  ],
  grounded: true,
  suggested_questions: ["신청 기간은 언제야?"],
  recent_notices: [
    {
      title: "최근 공지",
      url: "https://example.test/notice",
      source: "kumoh",
      published_at: "2026-07-14",
      topic_key: "academic",
      topic_label: "학사",
    },
  ],
};

describe("Home", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal(
      "requestAnimationFrame",
      vi.fn((callback: FrameRequestCallback) => {
        callback(0);
        return 1;
      }),
    );
  });

  it("renders the answer and follow-up data returned by the chat client", async () => {
    mockedRequestChat.mockResolvedValueOnce(reply);
    render(<Home />);

    fireEvent.change(screen.getByRole("textbox", { name: "질문 입력" }), {
      target: { value: "수강신청 방법" },
    });
    fireEvent.click(screen.getByRole("button", { name: "질문 보내기" }));

    expect(await screen.findByText(reply.content)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /수강신청 안내/ })).toHaveAttribute(
      "href",
      "https://example.test/course",
    );
    expect(screen.getByRole("button", { name: "신청 기간은 언제야?" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /최근 공지/ })).toHaveAttribute(
      "href",
      "https://example.test/notice",
    );
    expect(mockedRequestChat).toHaveBeenCalledWith("수강신청 방법", {
      apiUrl: "http://localhost:8000",
    });
  });

  it("requests an answer when an initial suggestion is clicked", async () => {
    mockedRequestChat.mockResolvedValueOnce(reply);
    render(<Home />);

    fireEvent.click(screen.getByRole("button", { name: "최근 수강신청 공지를 알려줘" }));

    await waitFor(() => {
      expect(mockedRequestChat).toHaveBeenCalledWith("최근 수강신청 공지를 알려줘", {
        apiUrl: "http://localhost:8000",
      });
    });
  });

  it("renders a timeout rejection as an assistant error message", async () => {
    mockedRequestChat.mockRejectedValueOnce(
      new Error("답변 요청 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요."),
    );
    render(<Home />);

    fireEvent.change(screen.getByRole("textbox", { name: "질문 입력" }), {
      target: { value: "응답 시간" },
    });
    fireEvent.click(screen.getByRole("button", { name: "질문 보내기" }));

    expect(
      await screen.findByText("답변 요청 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요."),
    ).toBeInTheDocument();
  });
});
