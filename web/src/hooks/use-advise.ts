"use client";

import { useState, useCallback, useEffect } from "react";
import { uploadDocument, adviseMessage } from "@/lib/api";
import type { AdviseResponse, DocumentUploadResponse } from "@/types/api";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  advice?: AdviseResponse | null;
}

const STORAGE_KEY = "advise_state";

export function useAdvise() {
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [uploadResult, setUploadResult] = useState<DocumentUploadResponse | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 마운트 시 sessionStorage에서 복원
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const saved = JSON.parse(raw);
      if (saved.documentId) setDocumentId(saved.documentId);
      if (saved.uploadResult) setUploadResult(saved.uploadResult);
      if (saved.sessionId) setSessionId(saved.sessionId);
      if (saved.messages) setMessages(saved.messages);
      if (saved.error) setError(saved.error);
    } catch {}
  }, []);

  // 상태 변경 시 sessionStorage에 저장
  useEffect(() => {
    if (isUploading || isLoading || !documentId) return;
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
        documentId, uploadResult, sessionId, messages, error,
      }));
    } catch {}
  }, [documentId, uploadResult, sessionId, messages, error, isUploading, isLoading]);

  const upload = useCallback(async (file: File) => {
    try {
      setIsUploading(true);
      setError(null);
      const res = await uploadDocument(file);
      setDocumentId(res.document_id);
      setUploadResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "업로드 실패");
    } finally {
      setIsUploading(false);
    }
  }, []);

  const sendMessage = useCallback(
    async (text: string) => {
      if (!documentId) return;
      setMessages((prev) => [...prev, { role: "user", content: text }]);
      setIsLoading(true);
      setError(null);

      try {
        const res = await adviseMessage({
          session_id: sessionId,
          document_id: documentId,
          message: text,
        });
        setSessionId(res.session_id);

        const content =
          res.advice?.reason ??
          res.error ??
          "응답을 생성할 수 없습니다.";

        setMessages((prev) => [
          ...prev,
          { role: "assistant", content, advice: res },
        ]);
      } catch (e) {
        setError(e instanceof Error ? e.message : "응답 실패");
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: "오류가 발생했습니다. 다시 시도해주세요." },
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    [documentId, sessionId],
  );

  const reset = useCallback(() => {
    setDocumentId(null);
    setUploadResult(null);
    setSessionId(null);
    setMessages([]);
    setError(null);
    try { sessionStorage.removeItem(STORAGE_KEY); } catch {}
  }, []);

  return {
    documentId,
    uploadResult,
    messages,
    isUploading,
    isLoading,
    error,
    upload,
    sendMessage,
    reset,
  };
}
