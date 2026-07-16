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
  it("parses clarification options and sends a confirmed intent when selected", async () => {
    const clarification = {
      response_type: "clarification",
      answer: "질문 의도를 이렇게 이해했습니다. 무엇을 찾을지 선택해 주세요.",
      sources: [],
      grounded: false,
      interpreted_intent: {
        topic_key: "registration",
        intent_key: "registration.main",
        label: "일반 수강신청 일정과 공지",
        example: "2026학년도 수강신청 일정과 유의사항",
      },
      clarification_options: [
        {
          topic_key: "registration",
          intent_key: "registration.main",
          label: "일반 수강신청 일정과 공지",
          example: "2026학년도 수강신청 일정과 유의사항",
        },
      ],
      suggested_questions: [],
      recent_notices: [],
    };
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(makeResponse(JSON.stringify(clarification), true));

    const reply = await requestChat("최근 수강신청 공지를 알려줘", {
      apiUrl: "https://api.example.test",
      confirmedIntentKey: "registration.main",
      fetchImpl,
    });

    expect(reply.responseType).toBe("clarification");
    expect(reply.clarificationOptions[0].intent_key).toBe("registration.main");
    expect(fetchImpl).toHaveBeenCalledWith(
      "https://api.example.test/api/chat",
      expect.objectContaining({
        body: JSON.stringify({
          question: "최근 수강신청 공지를 알려줘",
          confirmed_intent_key: "registration.main",
        }),
      }),
    );
  });

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
      responseType: "answer",
      sources: [source],
      grounded: true,
      interpretedIntent: null,
      clarificationOptions: [],
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
      responseType: "answer",
      sources: [],
      grounded: undefined,
      interpretedIntent: null,
      clarificationOptions: [],
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
    ["an unknown response type", { response_type: "unsupported" }],
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
    [
      "a malformed clarification option",
      {
        clarification_options: [
          {
            topic_key: "registration",
            intent_key: "registration.main",
            label: "수강신청",
          },
        ],
      },
    ],
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
    ["an empty answer", { answer: "   " }],
    ["an empty source title", { answer: "답변", sources: [{ ...source, title: "  " }] }],
    ["an empty source URL", { answer: "답변", sources: [{ ...source, url: "" }] }],
    ["an empty source name", { answer: "답변", sources: [{ ...source, source: "\t" }] }],
    [
      "an empty recent notice title",
      { answer: "답변", recent_notices: [{ ...notice, title: " " }] },
    ],
    [
      "an empty recent notice URL",
      { answer: "답변", recent_notices: [{ ...notice, url: "" }] },
    ],
    [
      "an empty recent notice name",
      { answer: "답변", recent_notices: [{ ...notice, source: "\n" }] },
    ],
    [
      "an empty recent notice topic key",
      { answer: "답변", recent_notices: [{ ...notice, topic_key: "  " }] },
    ],
    [
      "an empty recent notice topic label",
      { answer: "답변", recent_notices: [{ ...notice, topic_label: "" }] },
    ],
    [
      "an empty published date",
      { answer: "답변", sources: [{ ...source, published_at: "  " }] },
    ],
    ["an empty suggested question", { answer: "답변", suggested_questions: ["  "] }],
  ])("rejects successful payloads with %s", async (_description, fields) => {
    const fetchImpl = vi.fn().mockResolvedValue(
      makeResponse(JSON.stringify(fields), true),
    );

    await expect(
      requestChat("질문", { apiUrl: "https://api.example.test", fetchImpl }),
    ).rejects.toMatchObject({
      kind: "invalid-success",
      message: "서버 응답 형식을 확인할 수 없습니다.",
    });
  });

  it("rejects a successful payload with a non-http source URL", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      makeResponse(JSON.stringify({ answer: "답변", sources: [{ ...source, url: "javascript:alert(1)" }] }), true),
    );

    await expect(
      requestChat("질문", { apiUrl: "https://api.example.test", fetchImpl }),
    ).rejects.toMatchObject({ kind: "invalid-success" });
  });

  it.each([
    ["a credential-bearing source URL", { sources: [{ ...source, url: "https://user:pass@example.test/course" }] }],
    [
      "a credential-bearing recent notice URL",
      { recent_notices: [{ ...notice, url: "http://user:pass@example.test/notice" }] },
    ],
  ])("rejects a successful payload with %s", async (_description, fields) => {
    const fetchImpl = vi.fn().mockResolvedValue(
      makeResponse(JSON.stringify({ answer: "답변", ...fields }), true),
    );

    await expect(
      requestChat("질문", { apiUrl: "https://api.example.test", fetchImpl }),
    ).rejects.toMatchObject({
      kind: "invalid-success",
      message: "서버 응답 형식을 확인할 수 없습니다.",
    });
  });

  it.each([
    ["a source URL with a query", { sources: [{ ...source, url: "https://example.test/course?year=2026" }] }],
    [
      "a recent notice URL with a fragment",
      { recent_notices: [{ ...notice, url: "https://example.test/notice#details" }] },
    ],
  ])("accepts %s", async (_description, fields) => {
    const fetchImpl = vi.fn().mockResolvedValue(
      makeResponse(JSON.stringify({ answer: "답변", ...fields }), true),
    );

    await expect(
      requestChat("질문", { apiUrl: "https://api.example.test", fetchImpl }),
    ).resolves.toMatchObject({ content: "답변" });
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
    [
      "a label-less project API key detail",
      JSON.stringify({ detail: "요청 실패: sk-proj-FAKE_TOKEN_FOR_TEST_ONLY_1234567890" }),
      "application/json",
    ],
    [
      "a label-less API key in plain text",
      "요청 실패: sk-FAKE_TOKEN_FOR_TEST_ONLY_1234567890",
      "text/plain",
    ],
    ["a plain-text password detail", "PASSWORD = hunter2", "text/plain"],
    [
      "a RuntimeError with a Unix path",
      JSON.stringify({ detail: "RuntimeError: database connection failed at /srv/app/main.py" }),
      "application/json",
    ],
    ["a workspace absolute path", "오류 위치: /workspace/service/main.py", "text/plain"],
    ["a mounted data path", "오류 위치: /mnt/data", "text/plain"],
    ["a custom absolute path", "오류 위치: /custom/path", "text/plain"],
    ["a traversal from a public endpoint", "오류 위치: /api/health/../../etc", "text/plain"],
    ["a public endpoint with a query", "오류 위치: /api/health?auth=secret", "text/plain"],
    ["a public endpoint with a fragment", "오류 위치: /api/live#debug", "text/plain"],
    ["a public endpoint with an extra path", "오류 위치: /api/health/extra", "text/plain"],
    ["a public endpoint with a Python suffix", "오류 위치: /api/health.py", "text/plain"],
    ["a public endpoint with a log suffix", "오류 위치: /api/live.log", "text/plain"],
    ["a public endpoint with a hyphen suffix", "오류 위치: /api/live-debug", "text/plain"],
    ["a public endpoint with an underscore suffix", "오류 위치: /api/live_debug", "text/plain"],
    ["a public endpoint with an encoded path suffix", "오류 위치: /api/health%2Fetc", "text/plain"],
    ["a credential URL", "문서 안내: https://user:pass@kumoh.ac.kr/help", "text/plain"],
    ["a URL with a query", "문서 안내: https://kumoh.ac.kr/help?auth=secret", "text/plain"],
    ["a URL with a fragment", "문서 안내: https://kumoh.ac.kr/help#debug", "text/plain"],
    ["a URL with an empty query marker", "문서 안내: https://kumoh.ac.kr/help?", "text/plain"],
    ["a URL with an empty fragment marker", "문서 안내: https://kumoh.ac.kr/help#", "text/plain"],
    [
      "a generic Error detail",
      JSON.stringify({ detail: "Error: 데이터베이스 연결 실패" }),
      "application/json",
    ],
    [
      "a generic Exception detail",
      JSON.stringify({ detail: "Exception: 처리 실패" }),
      "application/json",
    ],
    [
      "an Authorization bearer credential",
      JSON.stringify({ detail: "Authorization: Bearer secret-token" }),
      "application/json",
    ],
    ["a Cookie credential", "Cookie: session=secret", "text/plain"],
    ["a Windows absolute path", "오류 위치: C:\\Users\\app\\main.py", "text/plain"],
    ["a technical message without Korean", "database connection failed", "text/plain"],
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

  it.each([
    [
      "the AI provider setup guidance",
      JSON.stringify({ detail: "AI_PROVIDER=openai 설정에는 OPENAI_API_KEY가 필요합니다." }),
      "application/json",
    ],
    ["a normal Korean error detail", JSON.stringify({ detail: "오류: 데이터베이스 연결 실패" }), "application/json"],
    ["the health endpoint guidance", "상태 확인은 /api/health를 호출하세요.", "text/plain"],
    ["the live endpoint guidance", "상태 확인은 /api/live를 호출하세요.", "text/plain"],
    ["the health endpoint with punctuation", "상태 확인: /api/health. 확인하세요.", "text/plain"],
    ["a safe HTTP URL", "문서 안내: http://kumoh.ac.kr/help", "text/plain"],
    ["a safe HTTPS URL", "문서 안내: https://kumoh.ac.kr/help", "text/plain"],
    ["a short non-secret sk word", "설정 키는 sk-공지 입니다.", "text/plain"],
    ["the Python command guidance", "문제 해결은 python -m ... 명령을 실행하세요.", "text/plain"],
  ])("preserves %s", async (_description, body, contentType) => {
    const fetchImpl = vi.fn().mockResolvedValue(makeResponse(body, false, contentType, 503));

    const message = body.startsWith("{") ? (JSON.parse(body) as { detail: string }).detail : body;
    await expect(
      requestChat("질문", { apiUrl: "https://api.example.test", fetchImpl }),
    ).rejects.toThrow(message);
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
