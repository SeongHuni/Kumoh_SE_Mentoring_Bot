import type { ReactNode } from "react";

import {
  ORDERED_ITEM,
  UNORDERED_ITEM,
  collectOrderedItems,
  collectUnorderedItems,
} from "./ListCollector";
import type { Source } from "./types";

type Props = {
  content: string;
  sources: Source[];
};

const inlineToken = /(\[(?:자료\s*)?(\d+)\])|(\[([^\]]+)\]\((https?:\/\/[^\s)]+)\))|(`[^`]+`)|(\*\*[^*]+\*\*)|(__[^_]+__)|(\*[^*\n]+\*)|(_[^_\n]+_)/g;

function InlineMarkdown({ text, sources }: { text: string; sources: Source[] }) {
  const nodes: ReactNode[] = [];
  let lastIndex = 0;

  for (const match of text.matchAll(inlineToken)) {
    const index = match.index ?? 0;
    if (index > lastIndex) {
      nodes.push(text.slice(lastIndex, index));
    }

    const token = match[0];
    const key = `${index}-${token}`;
    const citationNumber = Number(match[2]);

    if (match[1]) {
      const source = sources[citationNumber - 1];
      nodes.push(
        // 강의평은 원문 링크가 없다(url === null). 그럴 때는 링크로 만들지 않는다.
        source?.url ? (
          <a
            className="citation-link"
            href={source.url}
            key={key}
            target="_blank"
            rel="noreferrer"
            aria-label={`자료 ${citationNumber}: ${source.title} 원문 열기`}
          >
            [{citationNumber}]
          </a>
        ) : (
          <span className="citation-link unavailable" key={key}>
            [{citationNumber}]
          </span>
        ),
      );
    } else if (match[3] && match[4] && match[5]) {
      nodes.push(
        <a className="markdown-link" href={match[5]} key={key} target="_blank" rel="noreferrer">
          {match[4]}
        </a>,
      );
    } else if (match[6]) {
      nodes.push(<code key={key}>{token.slice(1, -1)}</code>);
    } else if (match[7] || match[8]) {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else if (match[9] || match[10]) {
      nodes.push(<em key={key}>{token.slice(1, -1)}</em>);
    }

    lastIndex = index + token.length;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return <>{nodes}</>;
}

function isBlockStart(line: string) {
  // 목록 판별과 같은 기준으로 들여쓰기를 허용한다.
  // 여기서만 들여쓴 불릿을 놓치면 문단이 그 줄을 삼켜 목록이 깨진다.
  return /^\s*(#{1,3}\s+|>\s?|[-*+]\s+|\d+[.)]\s+|```|---+$)/.test(line);
}

function Paragraph({ lines, sources }: { lines: string[]; sources: Source[] }) {
  return (
    <p>
      {lines.map((line, index) => (
        <span key={`${line}-${index}`}>
          <InlineMarkdown text={line} sources={sources} />
          {index < lines.length - 1 && <br />}
        </span>
      ))}
    </p>
  );
}

export function MessageMarkdown({ content, sources }: Props) {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let lineIndex = 0;

  while (lineIndex < lines.length) {
    const line = lines[lineIndex];
    if (!line.trim()) {
      lineIndex += 1;
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const Tag = `h${level + 2}` as "h3" | "h4" | "h5";
      blocks.push(
        <Tag key={`heading-${lineIndex}`}>
          <InlineMarkdown text={heading[2]} sources={sources} />
        </Tag>,
      );
      lineIndex += 1;
      continue;
    }

    if (line.startsWith("```")) {
      const codeLines: string[] = [];
      lineIndex += 1;
      while (lineIndex < lines.length && !lines[lineIndex].startsWith("```")) {
        codeLines.push(lines[lineIndex]);
        lineIndex += 1;
      }
      if (lineIndex < lines.length) lineIndex += 1;
      blocks.push(
        <pre key={`code-${lineIndex}`}>
          <code>{codeLines.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    if (/^---+$/.test(line)) {
      blocks.push(<hr key={`rule-${lineIndex}`} />);
      lineIndex += 1;
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quoteLines: string[] = [];
      while (lineIndex < lines.length && /^>\s?/.test(lines[lineIndex])) {
        quoteLines.push(lines[lineIndex].replace(/^>\s?/, ""));
        lineIndex += 1;
      }
      blocks.push(
        <blockquote key={`quote-${lineIndex}`}>
          <Paragraph lines={quoteLines} sources={sources} />
        </blockquote>,
      );
      continue;
    }

    const unordered = line.match(UNORDERED_ITEM);
    if (unordered) {
      const collected = collectUnorderedItems(lines, lineIndex);
      const items = collected.items;
      lineIndex = collected.nextIndex;
      blocks.push(
        <ul key={`unordered-${lineIndex}`}>
          {items.map((item, index) => (
            <li key={`${item}-${index}`}>
              <InlineMarkdown text={item} sources={sources} />
            </li>
          ))}
        </ul>,
      );
      continue;
    }

    const ordered = line.match(ORDERED_ITEM);
    if (ordered) {
      const collected = collectOrderedItems(lines, lineIndex);
      const items = collected.items;
      lineIndex = collected.nextIndex;
      blocks.push(
        <ol key={`ordered-${lineIndex}`}>
          {items.map((item, index) => (
            <li key={`${item.text}-${index}`}>
              <InlineMarkdown text={item.text} sources={sources} />
              {item.children.length > 0 && (
                <ul>
                  {item.children.map((child, childIndex) => (
                    <li key={`${child}-${childIndex}`}>
                      <InlineMarkdown text={child} sources={sources} />
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ol>,
      );
      continue;
    }

    const paragraph: string[] = [];
    while (
      lineIndex < lines.length &&
      lines[lineIndex].trim() &&
      !isBlockStart(lines[lineIndex])
    ) {
      paragraph.push(lines[lineIndex]);
      lineIndex += 1;
    }
    blocks.push(<Paragraph key={`paragraph-${lineIndex}`} lines={paragraph} sources={sources} />);
  }

  return <div className="message-markdown">{blocks}</div>;
}
