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

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isNullableNonEmptyString(value: unknown): value is string | null {
  return value === null || isNonEmptyString(value);
}

function isHttpUrl(value: unknown): value is string {
  if (!isNonEmptyString(value)) return false;

  try {
    const protocol = new URL(value).protocol;
    return protocol === "http:" || protocol === "https:";
  } catch {
    return false;
  }
}

function isPlainTextContentType(contentType: string): boolean {
  return contentType.toLowerCase().includes("text/plain");
}

const HTTP_URL_PATTERN = /https?:\/\/[^\s<>"']+/gi;
const PUBLIC_ENDPOINT_PATTERN = /\/api\/(?:health|live)(?![A-Za-z0-9_/?#])/gi;

function hasUnsafePosixPath(text: string): boolean {
  let hasUnsafeUrl = false;
  const withoutSafeUrls = text.replace(HTTP_URL_PATTERN, (candidate) => {
    try {
      const url = new URL(candidate);
      if (url.username || url.password || url.search || url.hash) {
        hasUnsafeUrl = true;
        return candidate;
      }
      return "";
    } catch {
      hasUnsafeUrl = true;
      return candidate;
    }
  });

  if (hasUnsafeUrl) return true;

  const withoutPublicEndpoints = withoutSafeUrls.replace(PUBLIC_ENDPOINT_PATTERN, "");
  return /(?:^|[^\w])\/(?!\/)[^\s"'<>)]*/i.test(withoutPublicEndpoints);
}

function hasUnsafeWindowsPath(text: string): boolean {
  return /(?:^|[^\w])[A-Za-z]:[\\/]/i.test(text);
}

function isSafeErrorMessage(text: string): boolean {
  const normalized = text.trim();
  return (
    normalized.length > 0 &&
    normalized.length <= 500 &&
    !/[\r\n]/.test(normalized) &&
    !/<\/?[a-z][^>]*>|<!doctype\s+html/i.test(normalized) &&
    !/\b(?:traceback|stack\s+trace)\b/i.test(normalized) &&
    !/(?:API_KEY|PASSWORD|SECRET|TOKEN)\s*[:=]\s*\S+/i.test(normalized) &&
    !/\b(?:Error|Exception|[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception))\s*:/i.test(normalized) &&
    !/\b(?:authorization|cookie)\s*:/i.test(normalized) &&
    !/\bbearer\s+\S+/i.test(normalized) &&
    !hasUnsafeWindowsPath(normalized) &&
    !hasUnsafePosixPath(normalized) &&
    /[가-힣]/.test(normalized)
  );
}

function getHttpErrorMessage(text: string, contentType: string): string {
  const payload = parseJsonObject(text);
  const detail = typeof payload?.detail === "string" ? payload.detail : undefined;
  const candidate = detail ?? (isPlainTextContentType(contentType) ? text : undefined);

  if (candidate !== undefined && isSafeErrorMessage(candidate)) {
    return candidate.trim();
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
  if (!isNonEmptyString(payload.answer)) {
    throw new ChatApiError(INVALID_SUCCESS_MESSAGE, "invalid-success");
  }

  const isRecord = (value: unknown): value is Record<string, unknown> =>
    value !== null && typeof value === "object" && !Array.isArray(value);
  const isSource = (value: unknown): value is Source =>
    isRecord(value) &&
    isNonEmptyString(value.title) &&
    isHttpUrl(value.url) &&
    isNonEmptyString(value.source) &&
    isNullableNonEmptyString(value.published_at) &&
    typeof value.score === "number" &&
    Number.isFinite(value.score);
  const isRecentNotice = (value: unknown): value is RecentNotice =>
    isRecord(value) &&
    isNonEmptyString(value.title) &&
    isHttpUrl(value.url) &&
    isNonEmptyString(value.source) &&
    isNullableNonEmptyString(value.published_at) &&
    isNonEmptyString(value.topic_key) &&
    isNonEmptyString(value.topic_label);
  const isNonEmptyStringElement = (value: unknown): value is string =>
    isNonEmptyString(value);
  const readArray = <T>(key: string, isElement: (value: unknown) => value is T): T[] => {
    const value = payload[key];
    if (value === undefined) return [];
    if (!Array.isArray(value) || !value.every(isElement)) {
      throw new ChatApiError(INVALID_SUCCESS_MESSAGE, "invalid-success");
    }
    return value;
  };

  let grounded: boolean | undefined;
  if (payload.grounded !== undefined) {
    if (typeof payload.grounded !== "boolean") {
      throw new ChatApiError(INVALID_SUCCESS_MESSAGE, "invalid-success");
    }
    grounded = payload.grounded;
  }

  return {
    content: payload.answer,
    sources: readArray("sources", isSource),
    grounded,
    suggested_questions: readArray("suggested_questions", isNonEmptyStringElement),
    recent_notices: readArray("recent_notices", isRecentNotice),
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

    if (timedOut) {
      throw new ChatApiError(TIMEOUT_MESSAGE, "timeout");
    }

    throw new ChatApiError(NETWORK_MESSAGE, "network");
  } finally {
    clearTimeout(timeoutId);
  }
}
