"use client";

import { useState } from "react";
import type { AnalysisResult } from "@/types/api";
import { RiskFindingCard } from "./risk-finding-card";
import { downloadRevisedContract } from "@/lib/api";
import {
  Shield,
  AlertTriangle,
  CheckCircle,
  Download,
  FileText,
  Loader2,
} from "lucide-react";

function RiskGauge({ score }: { score: number }) {
  const pct = (score / 10) * 100;
  const color =
    score >= 7 ? "text-red-600" : score >= 4 ? "text-yellow-600" : "text-green-600";
  const bg =
    score >= 7 ? "bg-red-500" : score >= 4 ? "bg-yellow-500" : "bg-green-500";

  return (
    <div className="flex items-center gap-4">
      <div className={`text-4xl font-bold ${color}`}>{score.toFixed(1)}</div>
      <div className="flex-1">
        <div className="text-sm font-medium">위험도 점수</div>
        <div className="mt-1 h-2 w-full rounded-full bg-muted">
          <div
            className={`h-full rounded-full transition-all ${bg}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
    </div>
  );
}

export function AnalysisResults({
  result,
  documentId,
}: {
  result: AnalysisResult;
  documentId: string;
}) {
  const [downloading, setDownloading] = useState<"docx" | "pdf" | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const sortedFindings = [...result.findings].sort((a, b) => {
    const order = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
    return (order[a.severity] ?? 4) - (order[b.severity] ?? 4);
  });

  const criticalCount = result.findings.filter(
    (f) => f.severity === "critical" || f.severity === "high",
  ).length;

  const hasSuggestions = result.findings.some((f) => f.suggested_text);

  const handleDownload = async (format: "docx" | "pdf") => {
    setDownloading(format);
    setDownloadError(null);
    try {
      await downloadRevisedContract(documentId, result.findings, format);
    } catch (e) {
      setDownloadError(
        e instanceof Error ? e.message : "다운로드에 실패했습니다.",
      );
    }
    setDownloading(null);
  };

  return (
    <div className="space-y-6">
      {/* Summary */}
      <div className="rounded-xl border bg-card p-6 space-y-4">
        <RiskGauge score={result.overall_risk_score} />
        <p className="text-sm text-muted-foreground">{result.risk_summary}</p>

        <div className="flex gap-4 text-sm">
          <div className="flex items-center gap-1.5">
            <AlertTriangle className="h-4 w-4 text-red-500" />
            <span>위험 조항 {criticalCount}개</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Shield className="h-4 w-4 text-blue-500" />
            <span>신뢰도 {Math.round(result.confidence * 100)}%</span>
          </div>
          {result.validation?.all_checks_passed && (
            <div className="flex items-center gap-1.5 text-green-600">
              <CheckCircle className="h-4 w-4" />
              <span>검증 통과</span>
            </div>
          )}
        </div>

        {result.warnings.length > 0 && (
          <div className="rounded-md bg-yellow-50 p-3 text-sm text-yellow-800">
            {result.warnings.map((w, i) => (
              <p key={i}>{w}</p>
            ))}
          </div>
        )}

        {/* 수정본 다운로드 */}
        {hasSuggestions && (
          <div className="rounded-md border bg-muted/30 p-4 space-y-3">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Download className="h-4 w-4" />
              수정 제안이 반영된 계약서 다운로드
            </div>
            <p className="text-xs text-muted-foreground">
              분석에서 제안된 수정 사항을 원문에 적용한 파일을 받을 수 있습니다.
              수정된 부분은 파란색으로 표시됩니다.
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => handleDownload("docx")}
                disabled={downloading !== null}
                className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {downloading === "docx" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <FileText className="h-3.5 w-3.5" />
                )}
                Word (.docx)
              </button>
              <button
                onClick={() => handleDownload("pdf")}
                disabled={downloading !== null}
                className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-muted disabled:opacity-50 transition-colors"
              >
                {downloading === "pdf" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <FileText className="h-3.5 w-3.5" />
                )}
                PDF
              </button>
            </div>
            {downloadError && (
              <p className="text-xs text-red-600">{downloadError}</p>
            )}
          </div>
        )}
      </div>

      {/* Findings */}
      <div>
        <h3 className="mb-3 text-lg font-semibold">
          분석 결과 ({result.findings.length}건)
        </h3>
        <div className="space-y-3">
          {sortedFindings.map((finding, i) => (
            <RiskFindingCard key={i} finding={finding} />
          ))}
        </div>
      </div>
    </div>
  );
}
