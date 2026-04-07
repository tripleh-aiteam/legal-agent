"use client";

import { useState } from "react";
import { useReview } from "@/hooks/use-review";
import { FileUpload } from "@/components/shared/file-upload";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { PerspectiveSelector } from "@/components/review/perspective-selector";
import { AnalysisResults } from "@/components/review/analysis-results";
import { FileText, RotateCcw, Eye, EyeOff } from "lucide-react";

export default function ReviewPage() {
  const { stage, uploadResult, documentDetail, reviewResult, error, upload, analyze, reset } =
    useReview();
  const [perspective, setPerspective] = useState<"갑" | "을" | "neutral">("neutral");
  const [showExtractedText, setShowExtractedText] = useState(false);

  return (
    <div className="mx-auto max-w-4xl p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">계약서 검토</h1>
          <p className="text-sm text-muted-foreground">
            계약서를 업로드하면 AI가 위험 조항을 분석합니다
          </p>
        </div>
        {stage !== "idle" && (
          <button
            onClick={reset}
            className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm hover:bg-muted"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            새로 시작
          </button>
        )}
      </div>

      {/* Upload */}
      {(stage === "idle" || stage === "uploading" || stage === "error") && (
        <FileUpload onUpload={upload} isUploading={stage === "uploading"} />
      )}

      {/* Uploaded — ready to analyze */}
      {stage === "uploaded" && uploadResult && (
        <div className="space-y-4">
          <div className="flex items-center gap-3 rounded-lg border bg-card p-4">
            <FileText className="h-8 w-8 text-primary" />
            <div className="flex-1">
              <p className="font-medium">{uploadResult.file_name}</p>
              <p className="text-sm text-muted-foreground">
                {uploadResult.clause_count}개 조항 | {uploadResult.page_count}페이지
              </p>
            </div>
          </div>

          {/* 추출 텍스트 미리보기 */}
          {documentDetail && (
            <div className="rounded-lg border bg-card">
              <button
                onClick={() => setShowExtractedText(!showExtractedText)}
                className="flex w-full items-center justify-between p-4 text-sm font-medium hover:bg-muted/50 transition-colors"
              >
                <span>추출된 텍스트 확인</span>
                {showExtractedText ? (
                  <EyeOff className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <Eye className="h-4 w-4 text-muted-foreground" />
                )}
              </button>
              {showExtractedText && (
                <div className="border-t px-4 pb-4">
                  {/* 조항별 보기 */}
                  {documentDetail.clauses.length > 0 && (
                    <div className="mt-3 space-y-2">
                      <p className="text-xs font-medium text-muted-foreground">
                        조항 분리 결과 ({documentDetail.clauses.length}개)
                      </p>
                      {documentDetail.clauses.map((clause, i) => (
                        <div key={i} className="rounded border-l-2 border-primary/30 bg-muted/30 p-3">
                          <p className="text-xs font-semibold text-primary">
                            {clause.clause_number} {clause.title ?? ""}
                          </p>
                          <p className="mt-1 text-xs text-foreground whitespace-pre-wrap">
                            {clause.content}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                  {/* 전체 원문 */}
                  <details className="mt-3">
                    <summary className="cursor-pointer text-xs font-medium text-muted-foreground hover:text-foreground">
                      전체 원문 보기
                    </summary>
                    <pre className="mt-2 max-h-96 overflow-auto rounded bg-muted p-3 text-xs whitespace-pre-wrap">
                      {documentDetail.raw_text}
                    </pre>
                  </details>
                </div>
              )}
            </div>
          )}

          <PerspectiveSelector value={perspective} onChange={setPerspective} />

          <button
            onClick={() => analyze(perspective)}
            className="w-full rounded-lg bg-primary px-4 py-3 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            분석 시작
          </button>
        </div>
      )}

      {/* Analyzing */}
      {stage === "analyzing" && (
        <LoadingSpinner
          className="py-16"
          message="계약서를 분석하고 있습니다. 잠시만 기다려주세요..."
        />
      )}

      {/* Results */}
      {stage === "done" && reviewResult?.analysis && (
        <AnalysisResults
          result={reviewResult.analysis}
          documentId={uploadResult?.document_id ?? ""}
        />
      )}

      {/* Error */}
      {error && (
        <div className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}
    </div>
  );
}
