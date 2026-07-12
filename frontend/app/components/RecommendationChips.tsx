"use client";

type Props = {
  questions: string[];
  disabled: boolean;
  onSelect: (question: string) => void;
};

export function RecommendationChips({ questions, disabled, onSelect }: Props) {
  if (questions.length === 0) return null;

  return (
    <section className="follow-up-section" aria-label="다음 질문 추천">
      <p className="follow-up-heading">다음 질문</p>
      <div className="recommendation-chips">
        {questions.map((question) => (
          <button
            key={question}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(question)}
          >
            {question}
          </button>
        ))}
      </div>
    </section>
  );
}
