"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

// 브라우저별 세션 ID. localStorage 에 한 번 만들어 두면 새로고침해도 같은
// 대화로 이어진다. 서버가 접속 주소(IP)로 사용자를 구분하는 방식은 같은
// 네트워크의 여러 기기가 하나의 IP 뒤로 묶이면(NAT) 대화가 섞일 수 있어서,
// 그것과 무관하게 항상 구분되도록 브라우저마다 고유 ID 를 만들어 보낸다.
// crypto.randomUUID() 는 보안 컨텍스트(HTTPS)에서만 쓸 수 있다.
// 발표장 접속은 IP:포트 로 하는 일반 HTTP 라 보안 컨텍스트가 아니고,
// iOS Safari 는 이때 이 함수를 막는다. 실제로 이것 때문에 페이지 전체가
// "client-side exception" 으로 죽었다. crypto 를 쓸 수 없는 환경에서도
// 절대 던지지 않는 대안으로 만든다.
function randomId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    try {
      return crypto.randomUUID();
    } catch {
      // 보안 컨텍스트가 아니면 여기로 떨어진다. 아래 대안으로 넘어간다.
    }
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function getSessionId(): string {
  const KEY = "se-chat-session-id";
  try {
    const existing = window.localStorage.getItem(KEY);
    if (existing) return existing;
    const created = randomId();
    window.localStorage.setItem(KEY, created);
    return created;
  } catch {
    // 개인정보 보호 모드 등으로 localStorage 를 못 쓰면 매 요청 새 ID.
    // 대화 이력이 안 이어질 뿐 기능은 그대로 동작한다.
    return randomId();
  }
}

import { ChatMessage } from "./components/ChatMessage";
import type {
  AssistantMessage,
  ClarificationOption,
  Message,
  UserMessage,
} from "./components/types";

// 빈 문자열이 기본값이다. 상대 경로(/api/chat)로 나가면 "지금 이 페이지를
// 연 주소" 그대로 요청하게 되어, 발표장에서 IP 가 뭐든 몇 명이 접속하든
// 항상 같은 오리진으로 맞물린다. next.config.ts 의 rewrite 가 그걸
// 컨테이너 내부에서 backend 로 넘긴다.
const configuredApiUrl = process.env.NEXT_PUBLIC_API_URL ?? "";
// Local-network and production proxies use `/api`, while the client app adds
// the endpoint path below. Keep both an origin URL and `/api` as valid config.
const apiUrl = configuredApiUrl.replace(/\/api\/?$/, "");
const suggestions = [
  "최근 수강신청 공지를 알려줘",
  "캡스톤디자인 신청 방법이 뭐야?",
  "취업 관련 프로그램을 찾아줘",
];

const initialMessage: AssistantMessage = {
  id: 0,
  role: "assistant",
  content:
    "안녕하세요! 학과 공지와 SE 게시판을 바탕으로 학사·진로 정보를 찾아드려요. 궁금한 내용을 질문해 주세요.",
  responseType: "answer",
  sources: [],
  suggested_questions: suggestions,
  recent_notices: [],
};

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([initialMessage]);
  const [question, setQuestion] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  // 서버 사이드 렌더링 시점에는 window 가 없으므로 useEffect 안에서만 만든다.
  // 렌더링 결과에 쓰이는 값이 아니라 제출 시점에만 읽으므로 초기값 null 로
  // 시작해도 사용자가 실제로 입력을 보낼 즈음에는 항상 채워져 있다.
  const sessionIdRef = useRef<string | null>(null);
  useEffect(() => {
    sessionIdRef.current = getSessionId();
  }, []);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const latestMessageRef = useRef<HTMLDivElement>(null);
  const hasConversation = messages.length > 1;

  useEffect(() => {
    if (messages.length < 2) return;

    requestAnimationFrame(() => {
      const latestMessage = latestMessageRef.current;
      if (typeof latestMessage?.scrollIntoView === "function") {
        latestMessage.scrollIntoView({ behavior: "smooth", block: "end" });
      }
    });
  }, [isLoading, messages.length]);

  async function submitQuestion(
    rawQuestion: string,
    options: { confirmedIntentKey?: string; appendUser?: boolean } = {},
  ) {
    const trimmed = rawQuestion.trim();
    if (trimmed.length < 2 || isLoading) return;

    // 되묻기 선택지를 고른 경우에는 같은 질문을 다시 말풍선으로 띄우지 않는다.
    if (options.appendUser !== false) {
      const userMessage: UserMessage = { id: Date.now(), role: "user", content: trimmed };
      setMessages((current) => [...current, userMessage]);
    }
    setQuestion("");
    setIsLoading(true);

    try {
      const response = await fetch(`${apiUrl}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: trimmed,
          session_id: sessionIdRef.current,
          ...(options.confirmedIntentKey
            ? { confirmed_intent_key: options.confirmedIntentKey }
            : {}),
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail ?? "답변을 불러오지 못했습니다.");
      }
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: "assistant",
          content: payload.answer,
          responseType: payload.response_type ?? "answer",
          sources: payload.sources ?? [],
          grounded: payload.grounded,
          interpretedIntent: payload.interpreted_intent ?? null,
          clarificationOptions: payload.clarification_options ?? [],
          originalQuestion: trimmed,
          suggested_questions: payload.suggested_questions ?? [],
          recent_notices: payload.recent_notices ?? [],
        },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: "assistant",
          content:
            error instanceof Error
              ? error.message
              : "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.",
          responseType: "no_answer",
          sources: [],
          grounded: false,
          interpretedIntent: null,
          clarificationOptions: [],
          suggested_questions: [],
          recent_notices: [],
        },
      ]);
    } finally {
      setIsLoading(false);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submitQuestion(question);
  }

  return (
    <main className="page-shell">
      <section
        className={`chat-frame ${hasConversation ? "has-conversation" : "is-empty"}`}
        aria-label="SE 멘토 챗봇"
      >
        <header className="topbar">
          <div className="brand-mark" aria-hidden="true">
            SE
          </div>
          <div className="brand-copy">
            <p className="eyebrow">금오공과대학교 소프트웨어전공</p>
            <h1>SE Mentor Bot</h1>
          </div>
        </header>

        <div className="message-list" aria-live="polite">
          {messages.map((message) => (
            <ChatMessage
              key={message.id}
              message={message}
              isLoading={isLoading}
              onSuggestion={(suggestion) => void submitQuestion(suggestion)}
              onClarify={(option, originalQuestion) =>
                void submitQuestion(originalQuestion, {
                  confirmedIntentKey: option.intent_key,
                  appendUser: false,
                })
              }
            />
          ))}

          {isLoading && (
            <article className="message-row assistant">
              <div className="avatar" aria-hidden="true">
                SE
              </div>
              <div className="typing" aria-label="답변 생성 중">
                <span />
                <span />
                <span />
              </div>
            </article>
          )}
        </div>

        <footer className="composer-wrap">
          <form className="composer" onSubmit={handleSubmit}>
            <label className="sr-only" htmlFor="question">
              질문 입력
            </label>
            <textarea
              id="question"
              ref={inputRef}
              rows={1}
              maxLength={500}
              placeholder="학사, 수업, 진로에 대해 질문해 보세요"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
            />
            <button
              className="send-button"
              type="submit"
              disabled={question.trim().length < 2 || isLoading}
              aria-label="질문 보내기"
            >
              <span>전송</span>
              <span aria-hidden="true">↑</span>
            </button>
          </form>
          <p className="disclaimer">답변은 참고용입니다. 중요한 학사 일정은 원문 공지를 다시 확인하세요.</p>
        </footer>
        <div ref={latestMessageRef} aria-hidden="true" />
      </section>
    </main>
  );
}
