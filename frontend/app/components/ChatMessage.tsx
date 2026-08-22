"use client";

import { IntentClarification } from "./IntentClarification";
import { RecommendationChips } from "./RecommendationChips";
import { MessageMarkdown } from "./MessageMarkdown";
import type { AssistantMessage, ClarificationOption, Message } from "./types";

type Props = {
  message: Message;
  isLoading: boolean;
  onSuggestion: (question: string) => void;
  // 되묻기 선택지를 고르면 원래 질문을 확정된 의도와 함께 다시 보낸다.
  onClarify?: (option: ClarificationOption, originalQuestion: string) => void;
};

function isAssistantMessage(message: Message): message is AssistantMessage {
  return message.role === "assistant";
}

export function ChatMessage({ message, isLoading, onSuggestion, onClarify }: Props) {
  const assistant = isAssistantMessage(message);
  const clarificationOptions = assistant ? message.clarificationOptions ?? [] : [];

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
        {assistant && clarificationOptions.length > 0 && onClarify && (
          <IntentClarification
            options={clarificationOptions}
            disabled={isLoading}
            onSelect={(option) =>
              onClarify(option, message.originalQuestion ?? message.content)
            }
          />
        )}
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
