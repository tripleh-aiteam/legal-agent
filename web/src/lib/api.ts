import type {
  AdviseRequest,
  AdviseResponse,
  DocumentDetail,
  DocumentUploadResponse,
  DraftContinueRequest,
  DraftResponse,
  DraftStartRequest,
  DraftGenerateRequest,
  LawLookupResponse,
  RiskFinding,
  ReviewRequest,
  ReviewResponse,
} from "@/types/api";

const BASE = "/api/v1";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `API 오류 (${res.status})`);
  }
  return res.json();
}

/* ── Documents ── */

export async function uploadDocument(
  file: File,
  docType?: string,
  language = "ko",
): Promise<DocumentUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  if (docType) form.append("doc_type", docType);
  form.append("language", language);
  return request<DocumentUploadResponse>("/documents/upload", {
    method: "POST",
    body: form,
  });
}

export async function getDocument(id: string): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/documents/${id}`);
}

/* ── Review ── */

export async function reviewDocument(req: ReviewRequest): Promise<ReviewResponse> {
  return request<ReviewResponse>("/analysis/review", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

/* ── Advise ── */

export async function adviseMessage(req: AdviseRequest): Promise<AdviseResponse> {
  return request<AdviseResponse>("/advise/message", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

/* ── Laws ── */

export async function lookupLaw(ref: string): Promise<LawLookupResponse> {
  return request<LawLookupResponse>(`/laws/lookup?ref=${encodeURIComponent(ref)}`);
}

/* ── Reports ── */

export async function downloadRevisedContract(
  documentId: string,
  findings: RiskFinding[],
  outputFormat: "docx" | "pdf" = "docx",
): Promise<void> {
  const res = await fetch(`${BASE}/reports/revised-contract`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      document_id: documentId,
      findings,
      output_format: outputFormat,
    }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `다운로드 실패 (${res.status})`);
  }

  // 파일 다운로드 트리거
  const blob = await res.blob();
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = disposition.match(/filename\*?=(?:UTF-8'')?(.+)/i);
  const filename = match
    ? decodeURIComponent(match[1].replace(/"/g, ""))
    : `수정본.${outputFormat}`;

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/* ── Draft ── */

export async function draftStart(userInput: string): Promise<DraftResponse> {
  const body: DraftStartRequest = { user_input: userInput };
  return request<DraftResponse>("/draft/start", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function draftContinue(
  sessionId: string,
  answer: string,
): Promise<DraftResponse> {
  const body: DraftContinueRequest = { session_id: sessionId, answer };
  return request<DraftResponse>("/draft/continue", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function draftGenerate(
  sessionId: string,
  outputFormat = "docx",
): Promise<DraftResponse> {
  const body: DraftGenerateRequest = { session_id: sessionId, output_format: outputFormat };
  return request<DraftResponse>("/draft/generate", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
