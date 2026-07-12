import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RecommendationChips } from "./RecommendationChips";

describe("RecommendationChips", () => {
  it("renders nothing when there are no questions", () => {
    render(<RecommendationChips questions={[]} disabled={false} onSelect={vi.fn()} />);

    expect(screen.queryByRole("region", { name: "다음 질문 추천" })).not.toBeInTheDocument();
  });

  it("calls onSelect with the clicked question", () => {
    const onSelect = vi.fn();
    render(
      <RecommendationChips
        questions={["이번 학기 개설강좌를 알려줘"]}
        disabled={false}
        onSelect={onSelect}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "이번 학기 개설강좌를 알려줘" }));

    expect(onSelect).toHaveBeenCalledWith("이번 학기 개설강좌를 알려줘");
  });

  it("does not select a disabled question", () => {
    const onSelect = vi.fn();
    render(
      <RecommendationChips
        questions={["수강신청 기간은?"]}
        disabled={true}
        onSelect={onSelect}
      />,
    );

    const button = screen.getByRole("button", { name: "수강신청 기간은?" });
    expect(button).toBeDisabled();

    fireEvent.click(button);

    expect(onSelect).not.toHaveBeenCalled();
  });
});
