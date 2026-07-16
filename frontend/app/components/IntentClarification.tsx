import type { ClarificationOption } from "./types";

type Props = {
  options: ClarificationOption[];
  disabled: boolean;
  onSelect: (option: ClarificationOption) => void;
};

export function IntentClarification({ options, disabled, onSelect }: Props) {
  if (options.length === 0) return null;

  return (
    <section className="intent-panel" aria-label="질문 의도 확인">
      <div className="intent-panel-heading">
        <span aria-hidden="true">01</span>
        <div>
          <strong>질문 의도 확인</strong>
          <p>가장 가까운 항목을 선택하면 해당 범위의 공지만 다시 확인합니다.</p>
        </div>
      </div>
      <div className="intent-options">
        {options.map((option) => (
          <button
            key={option.intent_key}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(option)}
          >
            <strong>{option.label}</strong>
            <span>예시 · {option.example}</span>
            <span className="intent-arrow" aria-hidden="true">
              →
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
