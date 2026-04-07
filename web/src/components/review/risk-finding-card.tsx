"use client";

import { useState } from "react";
import type { RiskFinding } from "@/types/api";
import { SeverityBadge } from "@/components/shared/severity-badge";
import { AlertTriangle, ArrowRight, BookOpen, ChevronDown, ChevronUp, ExternalLink, Loader2 } from "lucide-react";
import { lookupLaw } from "@/lib/api";

function LawReference({ lawRef }: { lawRef: string }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [lawContent, setLawContent] = useState<{
    found: boolean;
    content: string | null;
    article_title?: string;
    law_url?: string;
    message?: string;
  } | null>(null);

  const handleClick = async () => {
    if (open) {
      setOpen(false);
      return;
    }

    if (!lawContent) {
      setLoading(true);
      try {
        const res = await lookupLaw(lawRef);
        setLawContent(res);
      } catch {
        setLawContent({ found: false, content: null, message: "조문 조회에 실패했습니다." });
      }
      setLoading(false);
    }
    setOpen(true);
  };

  return (
    <div>
      <button
        onClick={handleClick}
        className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-1 text-xs text-blue-700 hover:bg-blue-100 transition-colors cursor-pointer"
      >
        <BookOpen className="h-3 w-3" />
        {lawRef}
        {loading ? (
          <Loader2 className="h-3 w-3 animate-spin" />
        ) : open ? (
          <ChevronUp className="h-3 w-3" />
        ) : (
          <ChevronDown className="h-3 w-3" />
        )}
      </button>
      {open && lawContent && (
        <div className="mt-2 rounded-md border bg-blue-50/50 p-3 text-xs">
          {lawContent.found && lawContent.content ? (
            <>
              <p className="font-semibold text-blue-800">
                {lawRef}
                {lawContent.article_title ? ` (${lawContent.article_title})` : ""}
              </p>
              <p className="mt-1.5 text-blue-900 whitespace-pre-wrap leading-relaxed">
                {lawContent.content}
              </p>
              {lawContent.law_url && (
                <a
                  href={lawContent.law_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 hover:underline"
                >
                  <ExternalLink className="h-3 w-3" />
                  국가법령정보센터에서 원문 확인
                </a>
              )}
            </>
          ) : (
            <div>
              <p className="text-muted-foreground">
                {lawContent.message || "해당 조문이 DB에 등록되어 있지 않습니다."}
              </p>
              {lawContent.law_url && (
                <a
                  href={lawContent.law_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-1.5 inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 hover:underline"
                >
                  <ExternalLink className="h-3 w-3" />
                  국가법령정보센터에서 직접 확인
                </a>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function RiskFindingCard({ finding }: { finding: RiskFinding }) {
  return (
    <div className="rounded-lg border p-4 space-y-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <SeverityBadge severity={finding.severity} />
          <span className="text-xs text-muted-foreground">{finding.category}</span>
        </div>
        <span className="text-xs text-muted-foreground">
          신뢰도 {Math.round(finding.confidence_score * 100)}%
        </span>
      </div>

      {/* Title & Description */}
      <div>
        <h4 className="font-semibold text-sm">{finding.title}</h4>
        <p className="mt-1 text-sm text-muted-foreground">{finding.description}</p>
      </div>

      {/* Original vs Suggested */}
      {finding.suggested_text && (
        <div className="space-y-2 text-sm">
          <div className="rounded-md bg-red-50 p-3">
            <div className="flex items-center gap-1 text-xs font-medium text-red-700 mb-1">
              <AlertTriangle className="h-3 w-3" />
              원문
            </div>
            <p className="text-red-900">{finding.original_text}</p>
          </div>
          <div className="flex justify-center">
            <ArrowRight className="h-4 w-4 text-muted-foreground" />
          </div>
          <div className="rounded-md bg-green-50 p-3">
            <div className="text-xs font-medium text-green-700 mb-1">수정 제안</div>
            <p className="text-green-900">{finding.suggested_text}</p>
            {finding.suggestion_reason && (
              <p className="mt-1 text-xs text-green-700">
                {finding.suggestion_reason}
              </p>
            )}
          </div>
        </div>
      )}

      {/* Legal references */}
      {(finding.related_law || finding.precedent_refs.length > 0) && (
        <div className="flex flex-wrap gap-2">
          {finding.related_law && (
            <LawReference lawRef={finding.related_law} />
          )}
          {finding.precedent_refs.map((ref) => (
            <span
              key={ref}
              className="inline-flex items-center rounded-full bg-purple-50 px-2 py-1 text-xs text-purple-700"
            >
              {ref}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
