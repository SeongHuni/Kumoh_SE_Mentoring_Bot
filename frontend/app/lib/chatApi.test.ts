import { describe, expect, it, vi } from "vitest";

import { requestChat } from "./chatApi";

import type { RecentNotice, Source } from "../components/types";

function makeResponse(body: string, ok: boolean, contentType = "application/json") {
  return {
    ok,
    headers: new Headers({ "content-type": contentType }),
    text: vi.fn().mockResolvedValue(body),
  } as unknown as Response;
}

const source: Source = {
  title: "수강신청 안내",
  url: "https://example.test/course",
  source: "kumoh",
  published_at: "2026-07-15",
  score: 0.98,
};

const notice: RecentNotice = {
  title: "최근 공지",
  url: "https://example.test/notice",
  source: "kumoh",
  published_at: "2026-07-14",
  topic_key: "academic",
  topic_label: "학사",
};

describe("requestChat", () => {
  it("normalizes the API URL and maps a successful chat response", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      makeResponse(
        JSON.stringify({
          answer: "수강신청은 포털에서 진행합니다.",
          sources: [source],
          grounded: true,
          suggested_questions: ["신청 기간은 언제야?"],
          recent_notices: [notice],
        }),
        true,
      ),
    );

    const reply = await requestChat("수강신청 방법", {
      apiUrl: "https://api.example.test///",
      fetchImpl,
    });

    expect(fetchImpl).toHaveBeenCalledWith(
      "https://api.example.test/api/chat",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: "수강신청 방법" }),
        signal: expect.any(AbortSignal),
      }),
    );
    expect(reply).toEqual({
      content: "수강신청은 포털에서 진행합니다.",
      sources: [source],
      grounded: true,
      suggested_questions: ["신청 기간은 언제야?"],
      recent_notices: [notice],
    });
  });

  it("preserves a FastAPI JSON detail message for an HTTP error", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(
        makeResponse(JSON.stringify({ detail: "이미 처리 중인 질문입니다." }), false),
      );

    await expect(
      requestChat("질문", { apiUrl: "https://api.example.test", fetchImpl }),
    ).rejects.toThrow("이미 처리 중인 질문입니다.");
  });

  it("hides HTML error bodies behind a readable fallback", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(
        makeResponse("<html><body>Internal Server Error</body></html>", false, "text/html"),
      );

    await expect(
      requestChat("질문", { apiUrl: "https://api.example.test", fetchImpl }),
    ).rejects.toThrow("답변을 불러오지 못했습니다.");
  });

  it("allows a short text/plain error message", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(makeResponse("질문이 너무 짧습니다.", false, "text/plain"));

    await expect(
      requestChat("질문", { apiUrl: "https://api.example.test", fetchImpl }),
    ).rejects.toThrow("질문이 너무 짧습니다.");
  });

  it("turns network failures into a readable Korean message", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(
      requestChat("질문", { apiUrl: "https://api.example.test", fetchImpl }),
    ).rejects.toThrow("서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
  });

  it("aborts a request after the timeout and reports a readable Korean message", async () => {
    vi.useFakeTimers();
    try {
      let requestSignal: AbortSignal | undefined;
      const fetchImpl = vi.fn((_: RequestInfo | URL, init?: RequestInit) => {
        requestSignal = init?.signal ?? undefined;
        return new Promise<Response>((_, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("The operation was aborted.", "AbortError"));
          });
        });
      });

      const promise = requestChat("질문", {
        apiUrl: "https://api.example.test",
        fetchImpl,
        timeoutMs: 50,
      });
      const rejection = expect(promise).rejects.toThrow(
        "답변 요청 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.",
      );

      await vi.advanceTimersByTimeAsync(50);

      await rejection;
      expect(requestSignal?.aborted).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it("uses empty arrays when successful list fields are missing", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(makeResponse(JSON.stringify({ answer: "답변입니다." }), true));

    await expect(
      requestChat("질문", { apiUrl: "https://api.example.test", fetchImpl }),
    ).resolves.toEqual({
      content: "답변입니다.",
      sources: [],
      grounded: undefined,
      suggested_questions: [],
      recent_notices: [],
    });
  });

  it("rejects a successful response with an invalid shape", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(makeResponse(JSON.stringify({ answer: 42 }), true));

    await expect(
      requestChat("질문", { apiUrl: "https://api.example.test", fetchImpl }),
    ).rejects.toThrow("서버 응답 형식을 확인할 수 없습니다.");
  });

  it("supports a fetch test double that exposes json without text", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ answer: "JSON 응답입니다." }),
    });

    await expect(
      requestChat("질문", { apiUrl: "https://api.example.test", fetchImpl }),
    ).resolves.toMatchObject({ content: "JSON 응답입니다." });
  });
});
