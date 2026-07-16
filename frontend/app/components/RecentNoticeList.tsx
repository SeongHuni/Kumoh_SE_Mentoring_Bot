import type { RecentNotice, ResponseType } from "./types";

type Props = {
  notices: RecentNotice[];
  responseType?: ResponseType;
};

export function RecentNoticeList({ notices, responseType = "answer" }: Props) {
  if (notices.length === 0) return null;

  const noAnswer = responseType === "no_answer";
  const label = noAnswer ? "답변 근거와 별개인 참고용 최근 공지" : "관련 최근 공지";

  return (
    <section className="recent-notice-section" aria-label={label}>
      <p className="notice-heading">{label}</p>
      <p className="notice-description">
        {noAnswer
          ? "위 답변의 근거가 아닌 참고 자료입니다."
          : "확인한 질문 의도와 관련된 최신 공지입니다."}
      </p>
      <div className="recent-notice-list">
        {notices.map((notice) => (
          <a
            className="notice-card"
            href={notice.url}
            key={`${notice.url}-${notice.title}`}
            target="_blank"
            rel="noreferrer"
          >
            <strong>{notice.title}</strong>
            <small>
              {notice.topic_label}
              {notice.published_at ? ` · ${notice.published_at}` : ""}
            </small>
            <span className="notice-arrow" aria-hidden="true">
              ↗
            </span>
          </a>
        ))}
      </div>
    </section>
  );
}
