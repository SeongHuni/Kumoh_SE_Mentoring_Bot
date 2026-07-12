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

export type AssistantMessage = {
  id: number;
  role: "assistant";
  content: string;
  sources: Source[];
  grounded?: boolean;
  suggested_questions: string[];
  recent_notices: RecentNotice[];
};

export type UserMessage = {
  id: number;
  role: "user";
  content: string;
};

export type Message = AssistantMessage | UserMessage;
