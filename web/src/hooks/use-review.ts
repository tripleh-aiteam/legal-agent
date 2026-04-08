"use client";

import { useState, useCallback, useEffect } from "react";
import { uploadDocument, reviewDocument, getDocument } from "@/lib/api";
import type { DocumentUploadResponse, DocumentDetail, ReviewResponse } from "@/types/api";

type ReviewStage = "idle" | "uploading" | "uploaded" | "analyzing" | "done" | "error";

const STORAGE_KEY = "review_state";

export function useReview() {
  const [stage, setStage] = useState<ReviewStage>("idle");
  const [uploadResult, setUploadResult] = useState<DocumentUploadResponse | null>(null);
  const [documentDetail, setDocumentDetail] = useState<DocumentDetail | null>(null);
  const [reviewResult, setReviewResult] = useState<ReviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 마운트 시 sessionStorage에서 복원
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const saved = JSON.parse(raw);
      if (saved.stage) setStage(saved.stage);
      if (saved.uploadResult) setUploadResult(saved.uploadResult);
      if (saved.documentDetail) setDocumentDetail(saved.documentDetail);
      if (saved.reviewResult) setReviewResult(saved.reviewResult);
      if (saved.error) setError(saved.error);
    } catch {}
  }, []);

  // 상태 변경 시 sessionStorage에 저장
  useEffect(() => {
    if (stage === "uploading" || stage === "analyzing" || stage === "idle") return;
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
        stage, uploadResult, documentDetail, reviewResult, error,
      }));
    } catch {}
  }, [stage, uploadResult, documentDetail, reviewResult, error]);

  const upload = useCallback(async (file: File) => {
    try {
      setStage("uploading");
      setError(null);
      const res = await uploadDocument(file);
      setUploadResult(res);
      try {
        const detail = await getDocument(res.document_id);
        setDocumentDetail(detail);
      } catch {
        // 상세 조회 실패해도 업로드는 성공
      }
      setStage("uploaded");
    } catch (e) {
      setError(e instanceof Error ? e.message : "업로드 실패");
      setStage("error");
    }
  }, []);

  const analyze = useCallback(
    async (perspective: "갑" | "을" | "neutral" = "neutral") => {
      if (!uploadResult) return;
      try {
        setStage("analyzing");
        setError(null);
        const res = await reviewDocument({
          document_id: uploadResult.document_id,
          perspective,
        });
        setReviewResult(res);
        setStage(res.status === "error" ? "error" : "done");
        if (res.error) setError(res.error);
      } catch (e) {
        setError(e instanceof Error ? e.message : "분석 실패");
        setStage("error");
      }
    },
    [uploadResult],
  );

  const reset = useCallback(() => {
    setStage("idle");
    setUploadResult(null);
    setDocumentDetail(null);
    setReviewResult(null);
    setError(null);
    try { sessionStorage.removeItem(STORAGE_KEY); } catch {}
  }, []);

  return { stage, uploadResult, documentDetail, reviewResult, error, upload, analyze, reset };
}
