"use client";

import { useState } from "react";
import type { InterviewQuestion } from "@/types/api";
import { Send, Info } from "lucide-react";

interface InterviewQuestionCardProps {
  question: InterviewQuestion;
  onAnswer: (answer: string) => void;
  isLoading: boolean;
}

export function InterviewQuestionCard({
  question,
  onAnswer,
  isLoading,
}: InterviewQuestionCardProps) {
  const [input, setInput] = useState("");
  const [subInputs, setSubInputs] = useState<Record<string, string>>({});

  const hasSubFields = question.sub_fields && question.sub_fields.length > 0;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isLoading) return;

    if (hasSubFields) {
      // sub_fields가 있으면 JSON으로 전달
      const allFilled = question.sub_fields!.every(
        (sf) => subInputs[sf.key]?.trim()
      );
      if (!allFilled) return;
      onAnswer(JSON.stringify(subInputs));
      setSubInputs({});
    } else {
      const text = input.trim();
      if (!text) return;
      setInput("");
      onAnswer(text);
    }
  };

  const updateSubInput = (key: string, value: string) => {
    setSubInputs((prev) => ({ ...prev, [key]: value }));
  };

  const useDefault = () => {
    if (question.default && !isLoading) {
      onAnswer(question.default);
    }
  };

  const isSubmitDisabled = hasSubFields
    ? !question.sub_fields!.every((sf) => subInputs[sf.key]?.trim()) || isLoading
    : !input.trim() || isLoading;

  return (
    <div className="rounded-xl border bg-card p-6 space-y-4">
      <div>
        <p className="text-sm font-medium">{question.question}</p>
        {question.warning && (
          <p className="mt-1 flex items-center gap-1 text-xs text-yellow-600">
            <Info className="h-3 w-3" />
            {question.warning}
          </p>
        )}
      </div>

      {/* Options (for contract_type selection) */}
      {question.options && (
        <div className="flex flex-wrap gap-2">
          {question.options.map((opt) => (
            <button
              key={opt}
              onClick={() => onAnswer(opt)}
              disabled={isLoading}
              className="rounded-lg border px-4 py-2 text-sm hover:bg-accent transition-colors disabled:opacity-50"
            >
              {opt}
            </button>
          ))}
        </div>
      )}

      {/* Sub-fields: 항목별 별도 입력 필드 */}
      {!question.options && hasSubFields && (
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="space-y-2">
            {question.sub_fields!.map((sf) => (
              <div key={sf.key} className="flex flex-col gap-1">
                <label className="text-xs font-medium text-muted-foreground">
                  {sf.label}
                </label>
                <input
                  type="text"
                  value={subInputs[sf.key] || ""}
                  onChange={(e) => updateSubInput(sf.key, e.target.value)}
                  placeholder={sf.placeholder || "입력하세요..."}
                  className="rounded-lg border bg-background px-4 py-2.5 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary"
                  disabled={isLoading}
                />
              </div>
            ))}
          </div>
          <button
            type="submit"
            disabled={isSubmitDisabled}
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm text-primary-foreground disabled:opacity-50 hover:bg-primary/90 transition-colors"
          >
            <Send className="h-4 w-4" />
            다음
          </button>
        </form>
      )}

      {/* Single text input */}
      {!question.options && !hasSubFields && (
        <form onSubmit={handleSubmit} className="space-y-3">
          {question.examples && (
            <p className="text-xs text-muted-foreground">
              예시: {question.examples}
            </p>
          )}
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={question.placeholder || "답변을 입력하세요..."}
              className="flex-1 rounded-lg border bg-background px-4 py-2.5 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary"
              disabled={isLoading}
            />
            <button
              type="submit"
              disabled={isSubmitDisabled}
              className="rounded-lg bg-primary px-4 py-2.5 text-primary-foreground disabled:opacity-50 hover:bg-primary/90 transition-colors"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
          {question.default && (
            <button
              type="button"
              onClick={useDefault}
              disabled={isLoading}
              className="text-xs text-primary hover:underline disabled:opacity-50"
            >
              기본값 사용: {question.default}
            </button>
          )}
        </form>
      )}
    </div>
  );
}
