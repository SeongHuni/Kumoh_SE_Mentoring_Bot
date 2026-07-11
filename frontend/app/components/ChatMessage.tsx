"use client";

import { RecommendationChips } from "./RecommendationChips";
import { RecentNoticeList } from "./RecentNoticeList";
import type { AssistantMessage, Message } from "./types";

type Props = {
  message: Message;
  isLoading: boolean;
  onSuggestion: (question: string) => void;
};

function isAssistantMessage(message: Message): message is AssistantMessage {
  return message.role === "assistant";
}

export function ChatMessage({ message, isLoading, onSuggestion }: Props) {
  const assistant = isAssistantMessage(message);
  const lines = message.content.split("\n");

  return (
    <article className={`message-row ${message.role}`}>
      <div className="avatar" aria-hidden="true">
        {assistant ? "SE" : "나"}
      </div>
      <div className="message-stack">
        <div className="message-bubble">
          {lines.map((line, index) => (
            <span key={`${message.id}-${index}`}>
              {line}
              {index < lines.length - 1 && <br />}
            </span>
          ))}
        </div>
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
            <RecentNoticeList notices={message.recent_notices} />
          </>
        )}
      </div>
    </article>
  );
}
