/* ── Document ── */

export interface DocumentUploadResponse {
  document_id: string;
  file_name: string;
  status: string;
  clause_count: number;
  page_count: number;
  message: string;
}

export interface DocumentDetail {
  id: string;
  file_name: string;
  file_type: string;
  status: string;
  clause_count: number;
  page_count: number;
  language: string;
  doc_type: string | null;
  security_scan_status: string;
  raw_text: string;
  clauses: ClauseInfo[];
}

export interface ClauseInfo {
  clause_number: string | null;
  title: string | null;
  content: string;
}

/* ── Review / Analysis ── */

export interface ReviewRequest {
  document_id: string;
  perspective: "갑" | "을" | "neutral";
  focus_areas?: string[];
}

export interface ReviewResponse {
  status: string;
  analysis: AnalysisResult | null;
  error: string | null;
}

export interface AnalysisResult {
  document_id: string;
  analysis_type: string;
  overall_risk_score: number;
  risk_summary: string;
  confidence: number;
  findings: RiskFinding[];
  validation: ValidationSummary | null;
  warnings: string[];
  processing_time_ms: number;
}

export interface RiskFinding {
  severity: "critical" | "high" | "medium" | "low" | "info";
  category: string;
  title: string;
  description: string;
  original_text: string;
  suggested_text: string | null;
  suggestion_reason: string | null;
  related_law: string | null;
  precedent_refs: string[];
  confidence_score: number;
}

export interface ValidationSummary {
  all_checks_passed: boolean;
  cross_validated: boolean;
  validator_model: string | null;
  issues: string[];
}

/* ── Laws ── */

export interface LawLookupResponse {
  found: boolean;
  law_name: string;
  article_number: string;
  article_title?: string;
  content: string | null;
  law_url?: string;
  message?: string;
}

/* ── Advise ── */

export interface AdviseRequest {
  session_id?: string | null;
  document_id: string;
  message: string;
}

export interface AdviseResponse {
  session_id: string;
  status: string;
  advice: AdviceContent | null;
  matched_clause: MatchedClause | null;
  error: string | null;
}

export interface AdviceContent {
  judgment: string;
  reason: string;
  legal_basis: {
    laws?: string[];
    precedents?: string[];
  };
  action_suggestion: string;
  follow_up_questions: string[];
  disclaimer: string;
}

export interface MatchedClause {
  clause_number: string | null;
  title: string | null;
  match_method: string | null;
}

/* ── Draft ── */

export interface DraftStartRequest {
  user_input: string;
}

export interface DraftContinueRequest {
  session_id: string;
  answer: string;
}

export interface DraftGenerateRequest {
  session_id: string;
  output_format?: string;
}

export interface DraftResponse {
  session_id: string;
  status: string;
  question: InterviewQuestion | null;
  progress: { collected: number; total: number } | null;
  contract_text: string | null;
  review_summary: Record<string, unknown> | null;
  output_path: string | null;
  message: string | null;
}

export interface SubField {
  key: string;
  label: string;
  placeholder?: string;
}

export interface InterviewQuestion {
  field: string;
  question: string;
  sub_fields?: SubField[];
  placeholder?: string | null;
  examples?: string | null;
  default?: string | null;
  warning?: string | null;
  is_required?: boolean;
  options?: string[];
}
