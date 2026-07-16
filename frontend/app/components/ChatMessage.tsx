"use client";

import type { Ref } from "react";

import { IntentClarification } from "./IntentClarification";
import { RecommendationChips } from "./RecommendationChips";
import { RecentNoticeList } from "./RecentNoticeList";
import type { AssistantMessage, ClarificationOption, Message } from "./types";

type Props = {
  message: Message;
  isLoading: boolean;
  onSuggestion: (question: string) => void;
  onIntentSelect?: (question: string, option: ClarificationOption) => void;
  messageRef?: Ref<HTMLElement>;
};

function isAssistantMessage(message: Message): message is AssistantMessage {
  return message.role === "assistant";
}

const sectionTitles = new Set(["확인한 최신 공지", "핵심 내용", "원문 확인"]);

function presentAnswerLine(line: string, assistant: boolean) {
  const trimmed = line.trim();
  if (!trimmed) return { className: "answer-spacer", text: "" };
  if (!assistant) return { className: "answer-line", text: line };
  if (sectionTitles.has(trimmed)) {
    return { className: "answer-section-title", text: trimmed };
  }
  if (/^\d+\.\s/.test(trimmed)) {
    return { className: "answer-notice-title", text: trimmed };
  }
  if (/^(?:분류|게시일)\s*·/.test(trimmed)) {
    return { className: "answer-meta", text: trimmed };
  }
  if (trimmed.startsWith("- ")) {
    return { className: "answer-bullet", text: trimmed.slice(2) };
  }
  if (/^출처\s*·/.test(trimmed)) {
    return { className: "answer-citation", text: trimmed };
  }
  return { className: "answer-line", text: line };
}

export function ChatMessage({
  message,
  isLoading,
  onSuggestion,
  onIntentSelect,
  messageRef,
}: Props) {
  const assistant = isAssistantMessage(message);
  const lines = message.content.split("\n");
  const responseType = assistant ? message.responseType ?? "answer" : "answer";
  const originalQuestion = assistant ? message.originalQuestion : undefined;

  return (
    <article ref={messageRef} className={`message-row ${message.role}`}>
      <div className="avatar" aria-hidden="true">
        {assistant ? "SE" : "나"}
      </div>
      <div className="message-stack">
        <div className={`message-bubble ${responseType}`}>
          {lines.map((line, index) => {
            const presented = presentAnswerLine(line, assistant);
            return (
              <span className={presented.className} key={`${message.id}-${index}`}>
                {presented.text}
              </span>
            );
          })}
        </div>
        {assistant &&
          responseType === "clarification" &&
          originalQuestion &&
          onIntentSelect && (
            <IntentClarification
              options={message.clarificationOptions ?? []}
              disabled={isLoading}
              onSelect={(option) => onIntentSelect(originalQuestion, option)}
            />
          )}
        {assistant && message.sources.length > 0 && (
          <div className="source-panel">
            <p className="source-heading">참고한 게시글</p>
            <div className="source-grid">
              {message.sources.map((source, index) => (
                <a
                  className="source-card"
                  href={source.url}
                  key={`${source.url}-${index}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <span className="source-index">{String(index + 1).padStart(2, "0")}</span>
                  <span className="source-copy">
                    <strong>{source.title}</strong>
                    <small>
                      {source.source === "kumoh" ? "학과 게시판" : "SE 게시판"}
                      {source.published_at ? ` · ${source.published_at}` : ""}
                    </small>
                  </span>
                  <span className="source-arrow" aria-hidden="true">
                    ↗
                  </span>
                </a>
              ))}
            </div>
          </div>
        )}
        {assistant && (
          <>
            <RecommendationChips
              questions={message.suggested_questions}
              disabled={isLoading}
              onSelect={onSuggestion}
            />
            <RecentNoticeList
              notices={message.recent_notices}
              responseType={responseType}
            />
          </>
        )}
      </div>
    </article>
  );
}
