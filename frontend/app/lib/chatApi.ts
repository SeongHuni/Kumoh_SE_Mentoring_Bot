import type { RecentNotice, Source } from "../components/types";

export const DEFAULT_TIMEOUT_MS = 15_000;

const TIMEOUT_MESSAGE = "답변 요청 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.";
const NETWORK_MESSAGE = "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.";
const INVALID_SUCCESS_MESSAGE = "서버 응답 형식을 확인할 수 없습니다.";
const HTTP_FALLBACK_MESSAGE = "답변을 불러오지 못했습니다.";

export type ChatReply = {
  content: string;
  sources: Source[];
  grounded?: boolean;
  suggested_questions: string[];
  recent_notices: RecentNotice[];
};

export type RequestChatOptions = {
  apiUrl: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
};

type ChatApiErrorKind = "timeout" | "network" | "http" | "invalid-success";

export class ChatApiError extends Error {
  readonly kind: ChatApiErrorKind;

  constructor(message: string, kind: ChatApiErrorKind) {
    super(message);
    this.name = "ChatApiError";
    this.kind = kind;
  }
}

function parseJsonObject(text: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(text);
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      return value as Record<string, unknown>;
    }
  } catch {
    // Non-JSON responses are handled by the caller's fallback path.
  }

  return null;
}

function isSafePlainText(text: string, contentType: string): boolean {
  const normalized = text.trim();
  return (
    contentType.toLowerCase().includes("text/plain") &&
    normalized.length > 0 &&
    normalized.length <= 500 &&
    !/^\s*</.test(normalized)
  );
}

function getHttpErrorMessage(text: string, contentType: string): string {
  const payload = parseJsonObject(text);
  if (typeof payload?.detail === "string" && payload.detail.trim().length > 0) {
    return payload.detail;
  }

  if (isSafePlainText(text, contentType)) {
    return text.trim();
  }

  return HTTP_FALLBACK_MESSAGE;
}

async function readResponseText(response: Response): Promise<string> {
  if (typeof response.text === "function") {
    return response.text();
  }

  const responseWithJson = response as Response & { json?: () => Promise<unknown> };
  if (typeof responseWithJson.json === "function") {
    return JSON.stringify(await responseWithJson.json());
  }

  return "";
}

function toChatReply(payload: Record<string, unknown>): ChatReply {
  if (typeof payload.answer !== "string") {
    throw new ChatApiError(INVALID_SUCCESS_MESSAGE, "invalid-success");
  }

  return {
    content: payload.answer,
    sources: Array.isArray(payload.sources) ? (payload.sources as Source[]) : [],
    grounded: typeof payload.grounded === "boolean" ? payload.grounded : undefined,
    suggested_questions: Array.isArray(payload.suggested_questions)
      ? (payload.suggested_questions as string[])
      : [],
    recent_notices: Array.isArray(payload.recent_notices)
      ? (payload.recent_notices as RecentNotice[])
      : [],
  };
}

export async function requestChat(
  question: string,
  { apiUrl, timeoutMs = DEFAULT_TIMEOUT_MS, fetchImpl = fetch }: RequestChatOptions,
): Promise<ChatReply> {
  const controller = new AbortController();
  let timedOut = false;
  const timeoutId = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  try {
    const response = await fetchImpl(`${apiUrl.replace(/\/+$/, "")}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
      signal: controller.signal,
    });
    const text = await readResponseText(response);
    const payload = parseJsonObject(text);

    if (!response.ok) {
      throw new ChatApiError(
        getHttpErrorMessage(text, response.headers?.get?.("content-type") ?? ""),
        "http",
      );
    }

    if (!payload) {
      throw new ChatApiError(INVALID_SUCCESS_MESSAGE, "invalid-success");
    }

    return toChatReply(payload);
  } catch (error) {
    if (error instanceof ChatApiError) {
      throw error;
    }

    if (timedOut || (error instanceof DOMException && error.name === "AbortError")) {
      throw new ChatApiError(TIMEOUT_MESSAGE, "timeout");
    }

    throw new ChatApiError(NETWORK_MESSAGE, "network");
  } finally {
    clearTimeout(timeoutId);
  }
}
