import type { AdviseResponse } from "@/types/api";
import { BookOpen, Lightbulb, Scale } from "lucide-react";

function JudgmentBadge({ judgment }: { judgment: string }) {
  const isRed = judgment.includes("위험");
  const isYellow = judgment.includes("주의");
  const bg = isRed
    ? "bg-red-100 text-red-800"
    : isYellow
      ? "bg-yellow-100 text-yellow-800"
      : "bg-green-100 text-green-800";

  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${bg}`}>
      {judgment}
    </span>
  );
}

export function AdviceCard({ data }: { data: AdviseResponse }) {
  const advice = data.advice;
  if (!advice) return null;

  return (
    <div className="space-y-3">
      {/* Judgment */}
      <JudgmentBadge judgment={advice.judgment} />

      {/* Reason */}
      <p className="text-sm">{advice.reason}</p>

      {/* Legal Basis */}
      {(advice.legal_basis?.laws?.length || advice.legal_basis?.precedents?.length) && (
        <div className="rounded-md bg-blue-50 p-3 space-y-1.5">
          <div className="flex items-center gap-1 text-xs font-medium text-blue-700">
            <BookOpen className="h-3 w-3" />
            법적 근거
          </div>
          {advice.legal_basis.laws?.map((law, i) => (
            <p key={i} className="text-xs text-blue-800">{law}</p>
          ))}
          {advice.legal_basis.precedents?.map((p, i) => (
            <p key={i} className="text-xs text-blue-700">{p}</p>
          ))}
        </div>
      )}

      {/* Action Suggestion */}
      {advice.action_suggestion && (
        <div className="flex items-start gap-2 text-sm">
          <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-yellow-500" />
          <span>{advice.action_suggestion}</span>
        </div>
      )}

      {/* Matched Clause */}
      {data.matched_clause && (
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Scale className="h-3 w-3" />
          관련 조항: {data.matched_clause.clause_number} {data.matched_clause.title}
        </div>
      )}

      {/* Disclaimer */}
      <p className="text-xs text-muted-foreground italic">{advice.disclaimer}</p>
    </div>
  );
}
