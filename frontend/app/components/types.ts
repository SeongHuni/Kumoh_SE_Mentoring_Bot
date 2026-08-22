export type Source = {
  title: string;
  url: string;
  source: string;
  published_at: string | null;
  score: number;
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
