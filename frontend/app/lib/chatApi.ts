import type {
  ClarificationOption,
  RecentNotice,
  ResponseType,
  Source,
} from "../components/types";

export const DEFAULT_TIMEOUT_MS = 15_000;

const TIMEOUT_MESSAGE = "답변 요청 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.";
const NETWORK_MESSAGE = "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.";
const INVALID_SUCCESS_MESSAGE = "서버 응답 형식을 확인할 수 없습니다.";
const HTTP_FALLBACK_MESSAGE = "답변을 불러오지 못했습니다.";

export type ChatReply = {
  content: string;
  responseType: ResponseType;
  sources: Source[];
  grounded?: boolean;
  interpretedIntent: ClarificationOption | null;
  clarificationOptions: ClarificationOption[];
  suggested_questions: string[];
  recent_notices: RecentNotice[];
};

export type RequestChatOptions = {
  apiUrl: string;
  confirmedIntentKey?: string;
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

function readResponseType(value: unknown): ResponseType {
  if (value === undefined) return "answer";
  if (value === "clarification" || value === "answer" || value === "no_answer") {
    return value;
  }
  throw new ChatApiError(INVALID_SUCCESS_MESSAGE, "invalid-success");
}

function isHttpUrl(value: unknown): value is string {
  if (!isNonEmptyString(value)) return false;

  try {
    const url = new URL(value);
    return (
      (url.protocol === "http:" || url.protocol === "https:") &&
      url.username === "" &&
      url.password === ""
    );
  } catch {
    return false;
  }
}

function isPlainTextContentType(contentType: string): boolean {
  return contentType.toLowerCase().includes("text/plain");
}

const HTTP_URL_PATTERN = /https?:\/\/[^\s<>"']+/gi;
const PUBLIC_ENDPOINT_TOKEN_PATTERN = /\/api\/(?:health|live)/gi;
const OPENAI_TOKEN_PATTERN = /\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}/i;
const KOREAN_PARTICLE_PATTERN = /^(?:에서|으로|정도|를|을|은|는|이|가|에|로|와|과|의|도|만)/;
const SENTENCE_PUNCTUATION_PATTERN = /^[.,!;:。、，．！…]/;

function removeSafeHttpUrls(text: string): { text: string; hasUnsafeUrl: boolean } {
  let hasUnsafeUrl = false;
  const withoutUrls = text.replace(HTTP_URL_PATTERN, (candidate) => {
    try {
      const url = new URL(candidate);
      if (
        url.username ||
        url.password ||
        url.search ||
        url.hash ||
        candidate.includes("?") ||
        candidate.includes("#")
      ) {
        hasUnsafeUrl = true;
        return candidate;
      }
      return "";
    } catch {
      hasUnsafeUrl = true;
      return candidate;
    }
  });

  return { text: withoutUrls, hasUnsafeUrl };
}

function isAllowedPublicEndpointSuffix(suffix: string): boolean {
  const particle = suffix.match(KOREAN_PARTICLE_PATTERN);
  const remainder = particle ? suffix.slice(particle[0].length) : suffix;

  if (remainder.length === 0 || /^\s/.test(remainder)) return true;
  if (!SENTENCE_PUNCTUATION_PATTERN.test(remainder)) return false;

  const afterPunctuation = remainder.slice(1);
  return (
    afterPunctuation.length === 0 ||
    /^\s/.test(afterPunctuation) ||
    /^[가-힣]/.test(afterPunctuation)
  );
}

function removeSafePublicEndpointMentions(text: string): string {
  return text.replace(PUBLIC_ENDPOINT_TOKEN_PATTERN, (token, offset, wholeText) => {
    const suffix = wholeText.slice(offset + token.length);
    return isAllowedPublicEndpointSuffix(suffix) ? "" : token;
  });
}

function hasUnsafePosixPath(text: string): boolean {
  const { text: withoutSafeUrls, hasUnsafeUrl } = removeSafeHttpUrls(text);
  if (hasUnsafeUrl) return true;

  const withoutPublicEndpoints = removeSafePublicEndpointMentions(withoutSafeUrls);
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
    !OPENAI_TOKEN_PATTERN.test(normalized) &&
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
  const isClarificationOption = (value: unknown): value is ClarificationOption =>
    isRecord(value) &&
    isNonEmptyString(value.topic_key) &&
    isNonEmptyString(value.intent_key) &&
    isNonEmptyString(value.label) &&
    isNonEmptyString(value.example);
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

  const responseType = readResponseType(payload.response_type);

  let interpretedIntent: ClarificationOption | null = null;
  if (payload.interpreted_intent !== undefined && payload.interpreted_intent !== null) {
    if (!isClarificationOption(payload.interpreted_intent)) {
      throw new ChatApiError(INVALID_SUCCESS_MESSAGE, "invalid-success");
    }
    interpretedIntent = payload.interpreted_intent;
  }
  const sources = readArray("sources", isSource);
  const clarificationOptions = readArray(
    "clarification_options",
    isClarificationOption,
  );
  if (
    responseType === "clarification" &&
    (grounded !== false ||
      sources.length > 0 ||
      interpretedIntent === null ||
      clarificationOptions.length === 0)
  ) {
    throw new ChatApiError(INVALID_SUCCESS_MESSAGE, "invalid-success");
  }
  if (responseType === "no_answer" && (grounded === true || sources.length > 0)) {
    throw new ChatApiError(INVALID_SUCCESS_MESSAGE, "invalid-success");
  }

  return {
    content: payload.answer,
    responseType,
    sources,
    grounded,
    interpretedIntent,
    clarificationOptions,
    suggested_questions: readArray("suggested_questions", isNonEmptyStringElement),
    recent_notices: readArray("recent_notices", isRecentNotice),
  };
}

export async function requestChat(
  question: string,
  {
    apiUrl,
    confirmedIntentKey,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    fetchImpl = fetch,
  }: RequestChatOptions,
): Promise<ChatReply> {
  const controller = new AbortController();
  let timedOut = false;
  const timeoutId = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  try {
    const body = {
      question,
      ...(confirmedIntentKey ? { confirmed_intent_key: confirmedIntentKey } : {}),
    };
    const response = await fetchImpl(`${apiUrl.replace(/\/+$/, "")}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
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
