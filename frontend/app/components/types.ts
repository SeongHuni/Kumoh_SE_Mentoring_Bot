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

export type ResponseType = "clarification" | "answer" | "no_answer";

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
