"use client";

import { useState, useCallback } from "react";
import { uploadDocument, reviewDocument, getDocument } from "@/lib/api";
import type { DocumentUploadResponse, DocumentDetail, ReviewResponse } from "@/types/api";

type ReviewStage = "idle" | "uploading" | "uploaded" | "analyzing" | "done" | "error";

export function useReview() {
  const [stage, setStage] = useState<ReviewStage>("idle");
  const [uploadResult, setUploadResult] = useState<DocumentUploadResponse | null>(null);
  const [documentDetail, setDocumentDetail] = useState<DocumentDetail | null>(null);
  const [reviewResult, setReviewResult] = useState<ReviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const upload = useCallback(async (file: File) => {
    try {
      setStage("uploading");
      setError(null);
      const res = await uploadDocument(file);
      setUploadResult(res);
      // 업로드 후 문서 상세(추출 텍스트 포함) 조회
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
  }, []);

  return { stage, uploadResult, documentDetail, reviewResult, error, upload, analyze, reset };
}
