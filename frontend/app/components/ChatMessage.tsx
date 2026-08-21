"use client";

import { RecommendationChips } from "./RecommendationChips";
import { MessageMarkdown } from "./MessageMarkdown";
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

  return (
    <article className={`message-row ${message.role}`}>
      <div className="avatar" aria-hidden="true">
        {assistant ? "SE" : "나"}
      </div>
      <div className="message-stack">
        <div className="message-bubble">
          {assistant ? (
            <MessageMarkdown content={message.content} sources={message.sources} />
          ) : (
            message.content
          )}
        </div>
        {assistant && message.sources.length > 0 && (
          <aside className="source-panel" aria-label="참고한 게시글">
            <span className="source-heading">참고한 게시글</span>
            <div className="source-inline">
              {message.sources.map((source, index) => (
                <a
                  className="source-link"
                  href={source.url}
                  key={`${source.url}-${index}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <span className="source-index">[{index + 1}]</span>
                  <span>{source.title}</span>
                </a>
              ))}
            </div>
          </aside>
        )}
        {assistant && (
          <>
            <RecommendationChips
              questions={message.suggested_questions}
              disabled={isLoading}
              onSelect={onSuggestion}
            />
          </>
        )}
      </div>
    </article>
  );
}
