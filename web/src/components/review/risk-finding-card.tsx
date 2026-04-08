"use client";

import { useState } from "react";
import type { RiskFinding } from "@/types/api";
import { SeverityBadge } from "@/components/shared/severity-badge";
import { AlertTriangle, ArrowRight, BookOpen, Brain, ChevronDown, ChevronUp, Database, ExternalLink, Loader2, ShieldCheck, ShieldAlert } from "lucide-react";
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
  const [showReasoning, setShowReasoning] = useState(false);

  return (
    <div className="rounded-lg border p-4 space-y-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <SeverityBadge severity={finding.severity} />
          <span className="text-xs text-muted-foreground">{finding.category}</span>
          {finding.rag_verified != null && (
            finding.rag_verified ? (
              <span className="inline-flex items-center gap-0.5 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700">
                <ShieldCheck className="h-3 w-3" />
                법률 근거 확인됨
              </span>
            ) : (
              <span className="inline-flex items-center gap-0.5 rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700">
                <ShieldAlert className="h-3 w-3" />
                AI 추론
              </span>
            )
          )}
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

      {/* AI 사고 과정 */}
      {finding.reasoning && (
        <div>
          <button
            onClick={() => setShowReasoning(!showReasoning)}
            className="flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-800 transition-colors"
          >
            <Brain className="h-3.5 w-3.5" />
            AI 분석 근거 보기
            {showReasoning ? (
              <ChevronUp className="h-3 w-3" />
            ) : (
              <ChevronDown className="h-3 w-3" />
            )}
          </button>
          {showReasoning && (
            <div className="mt-2 rounded-md border border-indigo-100 bg-indigo-50/50 p-3 text-xs text-indigo-900 whitespace-pre-wrap leading-relaxed">
              {finding.reasoning}
            </div>
          )}
        </div>
      )}

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

      {/* RAG 검색 근거 */}
      {(finding.rag_law_refs?.length || finding.rag_precedent_refs?.length) ? (
        <div className="rounded-md border border-slate-200 bg-slate-50 p-3 space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-medium text-slate-700">
            <Database className="h-3.5 w-3.5" />
            DB 검색 근거
          </div>
          {finding.rag_law_refs?.map((law, i) => (
            <div key={i} className="text-xs text-slate-600">
              <span className="font-medium">{law.law_name} {law.article_number}</span>
              {law.article_title ? ` (${law.article_title})` : ""}
              <p className="mt-0.5 text-slate-500">{law.content}</p>
            </div>
          ))}
          {finding.rag_precedent_refs?.map((p, i) => (
            <div key={i} className="text-xs text-slate-600">
              <span className="font-medium">{p.court} {p.case_number}</span>: {p.title}
              <p className="mt-0.5 text-slate-500">{p.summary}</p>
            </div>
          ))}
        </div>
      ) : null}

      {/* Legal references (기존) */}
      {(finding.related_law || finding.precedent_refs?.length > 0) && (
        <div className="flex flex-wrap gap-2">
          {finding.related_law && (
            <LawReference lawRef={finding.related_law} />
          )}
          {finding.precedent_refs?.map((ref) => (
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
