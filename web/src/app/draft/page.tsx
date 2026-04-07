"use client";

import { useState } from "react";
import { useDraft } from "@/hooks/use-draft";
import { DraftProgress } from "@/components/draft/draft-progress";
import { InterviewQuestionCard } from "@/components/draft/interview-question";
import { ContractPreview } from "@/components/draft/contract-preview";
import { LoadingSpinner } from "@/components/shared/loading-spinner";
import { RotateCcw, Send } from "lucide-react";

export default function DraftPage() {
  const {
    stage,
    currentQuestion,
    progress,
    contractText,
    reviewSummary,
    outputPath,
    isLoading,
    error,
    start,
    answer,
    generate,
    reset,
  } = useDraft();

  const [startInput, setStartInput] = useState("");

  const handleStart = (e: React.FormEvent) => {
    e.preventDefault();
    const text = startInput.trim();
    if (!text) return;
    setStartInput("");
    start(text);
  };

  return (
    <div className="mx-auto max-w-3xl p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">계약서 생성</h1>
          <p className="text-sm text-muted-foreground">
            대화형 인터뷰를 통해 맞춤 계약서를 생성합니다
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

      {/* Idle: Start input */}
      {stage === "idle" && (
        <form onSubmit={handleStart} className="space-y-4">
          <div className="rounded-xl border bg-card p-6 space-y-4">
            <p className="text-sm text-muted-foreground">
              어떤 계약서를 만들고 싶으신가요? 자유롭게 설명해주세요.
            </p>
            <div className="flex gap-2">
              <input
                type="text"
                value={startInput}
                onChange={(e) => setStartInput(e.target.value)}
                placeholder="예: 프리랜서 웹 개발 용역계약서를 만들어줘"
                className="flex-1 rounded-lg border bg-background px-4 py-2.5 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary"
              />
              <button
                type="submit"
                disabled={!startInput.trim()}
                className="rounded-lg bg-primary px-4 py-2.5 text-primary-foreground disabled:opacity-50 hover:bg-primary/90 transition-colors"
              >
                <Send className="h-4 w-4" />
              </button>
            </div>

            {/* Quick options */}
            <div className="flex flex-wrap gap-2">
              {["용역계약서", "비밀유지계약(NDA)", "근로계약서", "임대차계약서"].map(
                (opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => start(opt)}
                    className="rounded-full border px-3 py-1.5 text-xs hover:bg-accent transition-colors"
                  >
                    {opt}
                  </button>
                ),
              )}
            </div>
          </div>
        </form>
      )}

      {/* Interviewing */}
      {stage === "interviewing" && (
        <div className="space-y-4">
          {progress && (
            <DraftProgress collected={progress.collected} total={progress.total} />
          )}
          {currentQuestion && (
            <InterviewQuestionCard
              question={currentQuestion}
              onAnswer={answer}
              isLoading={isLoading}
            />
          )}
        </div>
      )}

      {/* Generating */}
      {stage === "generating" && !contractText && (
        <LoadingSpinner
          className="py-16"
          message="계약서를 생성하고 있습니다..."
        />
      )}

      {/* Interview complete — trigger generation */}
      {stage === "generating" && !contractText && !isLoading && (
        <button
          onClick={() => generate()}
          className="w-full rounded-lg bg-primary px-4 py-3 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          계약서 생성
        </button>
      )}

      {/* Completed */}
      {stage === "completed" && contractText && (
        <ContractPreview
          contractText={contractText}
          reviewSummary={reviewSummary}
          outputPath={outputPath}
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
