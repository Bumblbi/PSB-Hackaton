export type Kind = 'law' | 'contract' | 'internal' | 'amendment';
export type AnswerStatus =
  | 'ANSWERED'
  | 'PARTIAL'
  | 'INSUFFICIENT_EVIDENCE'
  | 'NEED_CLARIFICATION'
  | 'FALSE_PREMISE'
  | 'HISTORICAL_LAW_UNAVAILABLE'
  | 'OUT_OF_SCOPE'
  | 'DISALLOWED'
  | 'IGNORE_INJECTION';
export interface Citation {
  ref: number;
  document_id: string;
  version_id: string;
  chunk_id: string;
  locator: string;
  quote: string;
}
export interface Answer {
  message_id: string;
  status: AnswerStatus;
  answer: string;
  citations: Citation[];
  reason: string;
  missing_info: string[];
  clarifying_question: string | null;
  trace_id: string;
  timings_ms: Record<string, number>;
}
export interface ChatMessage {
  message_id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  answer: Answer | null;
}
export interface Chat {
  chat_id: string;
  title: string;
  messages: ChatMessage[];
}
export interface ChatSummary {
  chat_id: string;
  title: string;
  created_at: string;
  last_message_at: string | null;
  message_count: number;
}
export interface Page<T> {
  items: T[];
  total: number;
}
export interface DocumentInfo {
  document_id: string;
  version_id: string;
  title: string;
  kind: Kind;
  revision: string;
  source_name: string;
  source_hash: string;
  valid_from: string | null;
  valid_to: string | null;
  is_current_only: boolean;
  amends_document_id: string | null;
  chunk_count: number;
}
export interface Section {
  chunk_id: string;
  document_id: string;
  version_id: string;
  ordinal: number;
  locator: string;
  text: string;
  page: number | null;
}
export interface SourceDocument {
  document_id: string;
  title: string;
  version: DocumentInfo;
  sections: Section[];
}
export interface Health {
  status: string;
  db: string;
  chunks: number;
  index_version: string;
  llm_provider: string;
}
export interface QuestionInput {
  question: string;
  event_date?: string;
  document_id?: string;
  document_kind?: Kind;
}
