import { Download, FileText, CheckCircle, AlertTriangle } from "lucide-react";

interface ContractPreviewProps {
  contractText: string;
  reviewSummary?: Record<string, unknown> | null;
  outputPath?: string | null;
}

export function ContractPreview({
  contractText,
  reviewSummary,
  outputPath,
}: ContractPreviewProps) {
  const passed = reviewSummary?.passed;
  const score = reviewSummary?.score as number | undefined;
  const issues = (reviewSummary?.issues as string[]) ?? [];

  return (
    <div className="space-y-4">
      {/* Review Summary */}
      {reviewSummary && (
        <div
          className={`rounded-lg border p-4 ${
            passed ? "bg-green-50 border-green-200" : "bg-yellow-50 border-yellow-200"
          }`}
        >
          <div className="flex items-center gap-2 text-sm font-medium">
            {passed ? (
              <>
                <CheckCircle className="h-4 w-4 text-green-600" />
                <span className="text-green-800">
                  자체 검증 통과{score != null && ` (${score}/10점)`}
                </span>
              </>
            ) : (
              <>
                <AlertTriangle className="h-4 w-4 text-yellow-600" />
                <span className="text-yellow-800">
                  검토 의견 있음{score != null && ` (${score}/10점)`}
                </span>
              </>
            )}
          </div>
          {issues.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
              {issues.map((issue, i) => (
                <li key={i}>- {issue}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Download */}
      {outputPath && (
        <a
          href={outputPath}
          download
          className="inline-flex items-center gap-2 rounded-lg border bg-card px-4 py-2 text-sm font-medium hover:bg-accent transition-colors"
        >
          <Download className="h-4 w-4" />
          DOCX 다운로드
        </a>
      )}

      {/* Contract Text */}
      <div className="rounded-xl border bg-card">
        <div className="flex items-center gap-2 border-b px-4 py-3">
          <FileText className="h-4 w-4 text-primary" />
          <span className="text-sm font-medium">생성된 계약서</span>
        </div>
        <div className="prose prose-sm max-w-none p-6 whitespace-pre-wrap">
          {contractText}
        </div>
      </div>
    </div>
  );
}
