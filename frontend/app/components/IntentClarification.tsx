import type { ClarificationOption } from "./types";

type Props = {
  options: ClarificationOption[];
  disabled: boolean;
  onSelect: (option: ClarificationOption) => void;
};

// 선택지에 붙여 보여줄 짧은 설명.
//
// 서버가 주는 example 은 실제로 검색할 질의라서 label 을 거의 그대로 포함한다.
// ("MT 장소" -> "소프트웨어전공 MT 장소") 그걸 그대로 두 줄로 쓰면 같은 말이
// 두 번 보인다. 겹치는 부분을 빼고 남는 말이 있을 때만 보조 설명으로 쓴다.
function hintFor(option: ClarificationOption): string | null {
  const label = option.label.replace(/\s+/gu, "");
  const example = option.example.trim();
  if (!example) return null;

  const compact = example.replace(/\s+/gu, "");
  if (compact === label) return null;

  // label 의 모든 어절이 example 안에 있으면 사실상 같은 말로 본다.
  const covered = option.label
    .split(/\s+/u)
    .filter(Boolean)
    .every((word) => compact.includes(word.replace(/\s+/gu, "")));

  return covered ? null : example;
}

export function IntentClarification({ options, disabled, onSelect }: Props) {
  if (options.length === 0) return null;

  return (
    <section className="intent-panel" aria-label="질문 의도 확인">
      <p className="intent-panel-heading">어떤 것을 찾으시나요?</p>

      <div className="intent-options">
        {options.map((option) => {
          const hint = hintFor(option);
          return (
            <button
              key={option.intent_key}
              type="button"
              className="intent-option"
              disabled={disabled}
              onClick={() => onSelect(option)}
            >
              <span className="intent-option-text">
                <span className="intent-option-label">{option.label}</span>
                {hint && <span className="intent-option-hint">{hint}</span>}
              </span>
              <span className="intent-option-arrow" aria-hidden="true">
                →
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
