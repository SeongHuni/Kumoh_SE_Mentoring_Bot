"use client";

import { FormEvent, useRef, useState } from "react";

import { ChatMessage } from "./components/ChatMessage";
import type {
  AssistantMessage,
  ClarificationOption,
  Message,
  UserMessage,
} from "./components/types";
import { requestChat } from "./lib/chatApi";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const suggestions = [
  "최근 수강신청 공지를 알려줘",
  "캡스톤디자인 신청 방법이 뭐야?",
  "취업 관련 프로그램을 찾아줘",
];

const initialMessage: AssistantMessage = {
  id: 0,
  role: "assistant",
  content:
    "안녕하세요! 현재 금오공대 공식 공지를 바탕으로 학사·진로 정보를 찾아드려요. 중요한 일정은 원문 공지를 다시 확인해 주세요.",
  responseType: "answer",
  sources: [],
  interpretedIntent: null,
  clarificationOptions: [],
  suggested_questions: suggestions,
  recent_notices: [],
};

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([initialMessage]);
  const [question, setQuestion] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  async function submitQuestion(
    rawQuestion: string,
    options: { confirmedIntentKey?: string; appendUser?: boolean } = {},
  ) {
    const trimmed = rawQuestion.trim();
    if (trimmed.length < 2 || isLoading) return;

    if (options.appendUser !== false) {
      const userMessage: UserMessage = { id: Date.now(), role: "user", content: trimmed };
      setMessages((current) => [...current, userMessage]);
    }
    setQuestion("");
    setIsLoading(true);

    try {
      const reply = await requestChat(trimmed, {
        apiUrl,
        ...(options.confirmedIntentKey
          ? { confirmedIntentKey: options.confirmedIntentKey }
          : {}),
      });
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: "assistant",
          content: reply.content,
          responseType: reply.responseType,
          sources: reply.sources,
          grounded: reply.grounded,
          interpretedIntent: reply.interpretedIntent,
          clarificationOptions: reply.clarificationOptions,
          originalQuestion:
            reply.responseType === "clarification" ? trimmed : undefined,
          suggested_questions: reply.suggested_questions,
          recent_notices: reply.recent_notices,
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

  function handleIntentSelect(
    originalQuestion: string,
    option: ClarificationOption,
  ) {
    void submitQuestion(originalQuestion, {
      confirmedIntentKey: option.intent_key,
      appendUser: false,
    });
  }

  return (
    <main className="page-shell">
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />

      <section className="chat-frame" aria-label="SE 멘토 챗봇">
        <header className="topbar">
          <div className="brand-mark" aria-hidden="true">
            SE
          </div>
          <div className="brand-copy">
            <p className="eyebrow">SOFTWARE ENGINEERING</p>
            <h1>SE Mentor Bot</h1>
          </div>
          <div className="status-pill">
            <span className="status-dot" />
            RAG prototype
          </div>
        </header>

        <div className="intro-strip">
          <div>
            <span className="intro-label">OFFICIAL SOURCES</span>
            <strong>흩어진 학과 정보를 한 번에</strong>
          </div>
          <p>검색된 게시글만 근거로 답하고 원문 링크를 함께 제공합니다.</p>
        </div>

        <div className="message-list" aria-live="polite">
          {messages.map((message) => (
            <ChatMessage
              key={message.id}
              message={message}
              isLoading={isLoading}
              onSuggestion={(suggestion) => void submitQuestion(suggestion)}
              onIntentSelect={handleIntentSelect}
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
      </section>
    </main>
  );
}
