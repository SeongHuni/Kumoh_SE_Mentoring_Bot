"use client";

import { IntentClarification } from "./IntentClarification";
import { RecommendationChips } from "./RecommendationChips";
import { MessageMarkdown } from "./MessageMarkdown";
import type { AssistantMessage, ClarificationOption, Message, Source } from "./types";

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

// 답변 본문에서 실제로 인용한 자료 번호만 추린다.
//
// 검색은 top-k 개를 가져오지만 LLM이 전부 쓰지는 않는다. 측정해보니 문항당
// 평균 2개만 인용했다. 쓰지도 않은 자료까지 "참고한 게시글"로 보여주면
// 근거가 아닌 것을 근거처럼 제시하는 셈이라 인용된 것만 남긴다.
//
// 번호는 다시 매기지 않는다. 본문의 [3] 과 목록의 [3] 이 같은 자료를 가리켜야 한다.
function citedSourcesOf(content: string, sources: Source[]): Source[] {
  const cited = new Set<number>();
  for (const match of content.matchAll(/\[(\d{1,2})\]/gu)) {
    cited.add(Number(match[1]));
  }

  const picked = sources.filter((source) => cited.has(source.index));

  // 인용 표기가 하나도 없으면(모델이 규칙을 안 지킨 경우) 전부 보여준다.
  // 근거를 아예 감추는 것보다는 낫다.
  return picked.length > 0 ? picked : sources;
}

export function ChatMessage({ message, isLoading, onSuggestion, onClarify }: Props) {
  const assistant = isAssistantMessage(message);
  const clarificationOptions = assistant ? message.clarificationOptions ?? [] : [];
  const citedSources = assistant ? citedSourcesOf(message.content, message.sources) : [];

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
        {assistant && citedSources.length > 0 && (
          <aside className="source-panel" aria-label="참고한 게시글">
            <span className="source-heading">참고한 게시글</span>
            <div className="source-inline">
              {citedSources.map((source) => {
                const label =
                  source.kind === "review" && source.course
                    ? `${source.course}${source.professor ? ` (${source.professor})` : ""} 강의평`
                    : source.title;

                // 강의평은 원문 링크가 없으므로 링크가 아닌 텍스트로 보여준다.
                return source.url ? (
                  <a
                    className="source-link"
                    href={source.url}
                    key={source.index}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <span className="source-index">[{source.index}]</span>
                    <span>{label}</span>
                  </a>
                ) : (
                  <span className="source-link is-plain" key={source.index}>
                    <span className="source-index">[{source.index}]</span>
                    <span>{label}</span>
                  </span>
                );
              })}
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
