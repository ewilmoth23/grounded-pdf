export type ProcessingStatus = 'queued' | 'processing' | 'ready' | 'failed' | 'deleted';

export interface DocumentRecord {
  id: string;
  original_name: string;
  title: string | null;
  file_size: number;
  page_count: number;
  searchable_page_count: number;
  status: ProcessingStatus;
  processing_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface UploadResult {
  documents: DocumentRecord[];
  rejected: Array<{ filename: string; code: string; message: string }>;
}

export interface Citation {
  id: string;
  document_id: string;
  document_name: string;
  page_number: number;
  excerpt: string;
  retrieval_score: number | null;
  ordinal: number;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations: Citation[];
  created_at: string;
}

export type VerificationVerdict = 'supported' | 'weak' | 'unsupported';

export interface VerificationSource {
  document_id: string;
  document_name: string;
  page_number: number;
  excerpt: string;
}

export interface VerificationSentence {
  text: string;
  verdict: VerificationVerdict;
  score: number;
  source: VerificationSource | null;
}

export interface Verification {
  message_id: string;
  generated_at: string;
  sentences: VerificationSentence[];
}

export interface SearchMatch {
  document_id: string;
  document_name: string;
  page_number: number;
  excerpt: string;
  score: number;
}

export interface SearchResult {
  query: string;
  documents_available: boolean;
  matches: SearchMatch[];
}

export interface Conversation {
  id: string;
  title: string;
  document_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

export interface SafeSettings {
  environment: string;
  model_provider: 'ollama' | 'openai_compatible' | 'mock';
  model_name: string;
  embedding_model: string;
  chunk_size: number;
  chunk_overlap: number;
  retrieval_count: number;
  max_upload_mb: number;
  max_upload_batch_mb: number;
  max_upload_files: number;
  temperature: number;
  max_output_tokens: number;
  ocr_enabled: boolean;
}

export interface ApiErrorShape {
  error: { code: string; message: string; request_id?: string };
}
