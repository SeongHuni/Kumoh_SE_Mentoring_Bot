"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { ChatMessage } from "./components/ChatMessage";
import type {
  AssistantMessage,
  ClarificationOption,
  Message,
  UserMessage,
} from "./components/types";

const configuredApiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
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
