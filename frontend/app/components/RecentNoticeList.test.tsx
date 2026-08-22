import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RecentNoticeList } from "./RecentNoticeList";

describe("RecentNoticeList", () => {
  it("renders nothing when there are no notices", () => {
    render(<RecentNoticeList notices={[]} />);

    expect(screen.queryByRole("region", { name: "최근 공지" })).not.toBeInTheDocument();
  });

  it("renders a notice title, topic label, date, and canonical link", () => {
    render(
      <RecentNoticeList
        notices={[
          {
            title: "2026학년도 개설강좌 안내",
            url: "https://example.com/course",
            source: "kumoh",
            published_at: "2026-03-20",
            topic_key: "course_openings",
            topic_label: "개설강좌조회",
          },
        ]}
      />,
    );

    expect(screen.getByRole("region", { name: "최근 공지" })).toBeInTheDocument();
    expect(screen.getByText("최근 공지", { selector: ".notice-heading" })).toBeInTheDocument();
    expect(screen.getByText("2026학년도 개설강좌 안내")).toBeInTheDocument();
    expect(screen.getByText("개설강좌조회 · 2026-03-20")).toBeInTheDocument();
    const noticeLink = screen.getByRole("link", { name: /2026학년도 개설강좌 안내/ });
    expect(noticeLink).toHaveAttribute("href", "https://example.com/course");
    expect(noticeLink).toHaveClass("notice-card");
    expect(within(noticeLink).getByText("↗")).toHaveClass("notice-arrow");
  });
});
