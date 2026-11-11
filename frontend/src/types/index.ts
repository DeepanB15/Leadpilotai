export type Company = {
  id: string; name: string; website_url: string; normalized_domain: string; industry: string | null;
  linkedin_url: string | null; instagram_url: string | null; youtube_url: string | null;
  facebook_url: string | null; x_url: string | null; latest_status: string | null;
  last_researched_at: string | null; created_at: string; updated_at: string; platforms: string[];
};
export type Stats = { total: number; completed: number; processing: number; failed_or_partial: number; pending: number };
export type Page<T> = { items: T[]; total: number };

export type SourceStatus = {
  platform: string; source_url: string | null; access_status: string; verification_status: string | null;
  status_detail: string | null; documents: number;
};
export type Job = {
  id: string; company_id: string; company_name: string | null; status: string; progress_stage: string | null;
  attempt: number; model_id: string | null; pipeline_version: string | null; error_info: Record<string, unknown> | null;
  created_at: string; started_at: string | null; completed_at: string | null; sources: SourceStatus[];
};
export type JobStart = { job_id: string; company_id: string; status: string; message: string };

export type Evidence = { document_id: string; source_url: string; excerpt: string };
export type Finding = {
  id: string; finding_type: string; classification: "observed_fact" | "inference" | "unknown"; title: string;
  description: string; evidence: Evidence[]; confidence: "high" | "medium" | "low";
  confidence_factors: { points?: number; breakdown?: Record<string, number>; independent_sources?: number; reason?: string; capped_for_inference?: boolean };
  review_status: string;
};
export type NamedItem = { name: string; description: string };
export type Overview = {
  name: string; website: string; domain: string; industry: string | null;
  description?: string; business_model?: string; target_audience?: string[];
  products?: NamedItem[]; services?: NamedItem[]; market_positioning?: string;
  digital_presence?: { website: string; social: string }; content_themes?: string[];
};
export type Coverage = {
  platform: string; source_url: string | null; status: string; verification_status: string | null; detail: string | null;
  documents: number; last_checked_at: string | null;
};
export type SalesItem = { text: string; based_on_findings: string[] };
export type SalesPrep = {
  talking_points: SalesItem[]; prospect_questions: SalesItem[];
  value_proposition: SalesItem | null; suggested_next_action: SalesItem | null;
};
export type ProfileField = { field: string; value: string; classification: string; evidence: Evidence[]; description?: string };
export type ReportSource = {
  document_id: string; platform: string; document_type: string; url: string; title: string | null;
  collected_at: string; published_at: string | null; verification_status: string;
};
export type Report = {
  id: string; company_id: string; job_id: string | null; version: number; created_at: string;
  overview: Overview; research_coverage: Coverage[]; findings: Finding[]; sales_preparation: SalesPrep;
  limitations: string[]; sources: ReportSource[]; profile: { version: number | null; fields: ProfileField[] };
  analysis: { status: string; error: string | null }; job_status: string;
  model_id: string | null; prompt_version: string; schema_version: string; pipeline_version: string; generated_at: string;
};
export type ReportSummary = { id: string; version: number; created_at: string; job_id: string | null };
export type SourceDoc = {
  id: string; document_type: string; url: string; title: string | null; content: string;
  published_at: string | null; collected_at: string;
};
export type Source = {
  id: string; platform: string; source_type: string; source_url: string; discovery_method: string | null;
  verification_status: string; access_status: string; status_detail: string | null;
  profile_metadata: Record<string, unknown> | null; last_checked_at: string | null; document_count: number;
  documents?: SourceDoc[] | null;
};
export type SourceList = { items: Source[]; coverage: Coverage[] };
export type ImportRow = {
  row: number; status: "valid" | "duplicate" | "invalid"; normalized_domain: string | null; errors: string[];
  data: Record<string, string>;
};
export type ImportResult = {
  mode: string; summary: { total: number; valid: number; duplicates: number; invalid: number };
  rows: ImportRow[]; created_company_ids: string[];
};
