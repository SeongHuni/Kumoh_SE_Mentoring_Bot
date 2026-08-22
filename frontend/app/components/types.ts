// 서버는 검색 결과를 걸러내지 않고 그대로, 같은 순서로 보낸다.
// 답변 본문의 [1], [2] 가 sources[N-1] 을 가리키므로 순서를 바꾸면 안 된다.
// 화면에서 무엇을 보여줄지는 프론트가 정한다(실제로 인용된 것만).
export type Source = {
  index: number;
  title: string;
  // 에브리타임 강의평은 원문 링크가 없어 null 이다.
  url: string | null;
  source: string;
  published_at: string | null;
  score: number;
  kind: "notice" | "review";
  // 강의평일 때만 채워진다. 링크 대신 "과목 (교수)" 로 표시한다.
  course: string | null;
  professor: string | null;
};

export type RecentNotice = {
  title: string;
  url: string;
  source: string;
  published_at: string | null;
  topic_key: string;
  topic_label: string;
};

// 서버가 무엇을 했는지 구분한다.
//   answer        검색 결과를 근거로 답했다
//   clarification 대상이 특정되지 않아 되물었다 (검색·생성 모델을 호출하지 않았다)
//   no_answer     근거가 없거나 범위 밖이라 답하지 않았다
export type ResponseType = "clarification" | "answer" | "no_answer";

// 되묻기 선택지. 사용자가 고르면 intent_key 를 그대로 서버에 돌려보내
// 다시 되묻지 않고 그 주제로 바로 검색하게 한다.
export type ClarificationOption = {
  topic_key: string;
  intent_key: string;
  label: string;
  example: string;
};

export type AssistantMessage = {
  id: number;
  role: "assistant";
  content: string;
  responseType?: ResponseType;
  sources: Source[];
  grounded?: boolean;
  interpretedIntent?: ClarificationOption | null;
  clarificationOptions?: ClarificationOption[];
  originalQuestion?: string;
  suggested_questions: string[];
  recent_notices: RecentNotice[];
};

export type UserMessage = {
  id: number;
  role: "user";
  content: string;
};

export type Message = AssistantMessage | UserMessage;
