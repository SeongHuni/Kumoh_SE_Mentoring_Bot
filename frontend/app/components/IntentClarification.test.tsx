import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { IntentClarification } from "./IntentClarification";


describe("IntentClarification", () => {
  it("shows readable intent examples and returns the selected option", () => {
    const onSelect = vi.fn();
    const option = {
      topic_key: "registration",
      intent_key: "registration.main",
      label: "일반 수강신청 일정과 공지",
      example: "2026학년도 수강신청 일정과 유의사항",
    };

    render(
      <IntentClarification options={[option]} disabled={false} onSelect={onSelect} />,
    );

    expect(screen.getByRole("region", { name: "질문 의도 확인" })).toBeInTheDocument();
    expect(screen.getByText(new RegExp(option.example))).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /일반 수강신청 일정과 공지/ }));
    expect(onSelect).toHaveBeenCalledWith(option);
  });
});
