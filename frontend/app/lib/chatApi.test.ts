import { describe, expect, it, vi } from "vitest";

import { requestChat } from "./chatApi";

import type { RecentNotice, Source } from "../components/types";

function makeResponse(
  body: string,
  ok: boolean,
  contentType = "application/json",
  status = ok ? 200 : 500,
) {
  return {
    ok,
    status,
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

  it("preserves a FastAPI JSON detail message for an HTTP 409 error", async () => {
    const response = makeResponse(
      JSON.stringify({ detail: "이미 처리 중인 질문입니다." }),
      false,
      "application/json",
      409,
    );
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(response);

    await expect(
      requestChat("질문", { apiUrl: "https://api.example.test", fetchImpl }),
    ).rejects.toThrow("이미 처리 중인 질문입니다.");
    expect(response.status).toBe(409);
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

  it.each([
    ["a null source", { sources: [null] }],
    ["a numeric source", { sources: [42] }],
    [
      "a malformed recent notice",
      {
        recent_notices: [
          {
            title: "공지",
            url: "https://example.test/notice",
            source: "kumoh",
            published_at: null,
            topic_key: "academic",
          },
        ],
      },
    ],
    ["a non-string suggested question", { suggested_questions: [42] }],
  ])("rejects successful payloads with %s", async (_description, fields) => {
    const fetchImpl = vi.fn().mockResolvedValue(
      makeResponse(JSON.stringify({ answer: "답변입니다.", ...fields }), true),
    );

    await expect(
      requestChat("질문", { apiUrl: "https://api.example.test", fetchImpl }),
    ).rejects.toMatchObject({
      kind: "invalid-success",
      message: "서버 응답 형식을 확인할 수 없습니다.",
    });
  });

  it.each([
    [
      "a JSON traceback detail",
      JSON.stringify({ detail: "Traceback (most recent call last): handler failed" }),
      "application/json",
    ],
    ["an HTML detail", JSON.stringify({ detail: "<html>server failure</html>" }), "application/json"],
    ["a multiline technical detail", JSON.stringify({ detail: "첫 줄\nstack trace: 두 번째 줄" }), "application/json"],
    ["a JSON API key detail", JSON.stringify({ detail: "OPENAI_API_KEY: sk-live-value" }), "application/json"],
    ["a plain-text password detail", "PASSWORD = hunter2", "text/plain"],
  ])("hides %s behind the HTTP fallback", async (_description, body, contentType) => {
    const fetchImpl = vi.fn().mockResolvedValue(makeResponse(body, false, contentType));

    await expect(
      requestChat("질문", { apiUrl: "https://api.example.test", fetchImpl }),
    ).rejects.toThrow("답변을 불러오지 못했습니다.");
  });

  it("preserves a safe configuration-name detail from a 503 response", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      makeResponse(
        JSON.stringify({ detail: "OPENAI_API_KEY가 필요합니다" }),
        false,
        "application/json",
        503,
      ),
    );

    await expect(
      requestChat("질문", { apiUrl: "https://api.example.test", fetchImpl }),
    ).rejects.toThrow("OPENAI_API_KEY가 필요합니다");
  });

  it("treats an immediate AbortError as a network failure when the timer did not fire", async () => {
    const fetchImpl = vi
      .fn()
      .mockRejectedValue(new DOMException("The operation was aborted.", "AbortError"));

    await expect(
      requestChat("질문", { apiUrl: "https://api.example.test", fetchImpl }),
    ).rejects.toMatchObject({
      kind: "network",
      message: "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.",
    });
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
