import type { RecentNotice } from "./types";

type Props = {
  notices: RecentNotice[];
};

export function RecentNoticeList({ notices }: Props) {
  if (notices.length === 0) return null;

  return (
    <section className="recent-notice-section" aria-label="최근 공지">
      <p className="notice-heading">최근 공지</p>
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
