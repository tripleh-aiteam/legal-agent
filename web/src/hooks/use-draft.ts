"use client";

import { useState, useCallback } from "react";
import { draftStart, draftContinue, draftGenerate } from "@/lib/api";
import type { DraftResponse, InterviewQuestion } from "@/types/api";

type DraftStage = "idle" | "interviewing" | "generating" | "completed" | "error";

export function useDraft() {
  const [stage, setStage] = useState<DraftStage>("idle");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [currentQuestion, setCurrentQuestion] = useState<InterviewQuestion | null>(null);
  const [progress, setProgress] = useState<{ collected: number; total: number } | null>(null);
  const [contractText, setContractText] = useState<string | null>(null);
  const [reviewSummary, setReviewSummary] = useState<Record<string, unknown> | null>(null);
  const [outputPath, setOutputPath] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleResponse = useCallback((res: DraftResponse) => {
    setSessionId(res.session_id);
    setCurrentQuestion(res.question ?? null);
    setProgress(res.progress ?? null);
    setContractText(res.contract_text ?? null);
    setReviewSummary(res.review_summary ?? null);
    setOutputPath(res.output_path ?? null);

    if (res.status === "completed") {
      setStage("completed");
    } else if (res.status === "generating" || res.status === "reviewing") {
      setStage("generating");
    } else if (res.status === "interviewing") {
      setStage("interviewing");
    } else if (res.status === "error") {
      setStage("error");
    }
  }, []);

  const start = useCallback(async (userInput: string) => {
    try {
      setIsLoading(true);
      setError(null);
      setStage("interviewing");
      const res = await draftStart(userInput);
      handleResponse(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "시작 실패");
      setStage("error");
    } finally {
      setIsLoading(false);
    }
  }, [handleResponse]);

  const answer = useCallback(async (text: string) => {
    if (!sessionId) return;
    try {
      setIsLoading(true);
      setError(null);
      const res = await draftContinue(sessionId, text);
      handleResponse(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "응답 처리 실패");
      setStage("error");
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, handleResponse]);

  const generate = useCallback(async (format = "docx") => {
    if (!sessionId) return;
    try {
      setIsLoading(true);
      setError(null);
      setStage("generating");
      const res = await draftGenerate(sessionId, format);
      handleResponse(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "생성 실패");
      setStage("error");
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, handleResponse]);

  const reset = useCallback(() => {
    setStage("idle");
    setSessionId(null);
    setCurrentQuestion(null);
    setProgress(null);
    setContractText(null);
    setReviewSummary(null);
    setOutputPath(null);
    setError(null);
  }, []);

  return {
    stage,
    sessionId,
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
  };
}
