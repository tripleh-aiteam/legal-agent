"use client";

import { useAdvise } from "@/hooks/use-advise";
import { FileUpload } from "@/components/shared/file-upload";
import { AdviseChat } from "@/components/advise/advise-chat";
import { FileText, RotateCcw } from "lucide-react";

export default function AdvisePage() {
  const {
    documentId,
    uploadResult,
    messages,
    isUploading,
    isLoading,
    error,
    upload,
    sendMessage,
    reset,
  } = useAdvise();

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div>
          <h1 className="text-xl font-bold">법률 상담</h1>
          {uploadResult && (
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <FileText className="h-3 w-3" />
              {uploadResult.file_name} ({uploadResult.clause_count}개 조항)
            </p>
          )}
        </div>
        {documentId && (
          <button
            onClick={reset}
            className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm hover:bg-muted"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            새로 시작
          </button>
        )}
      </div>

      {/* Upload or Chat */}
      {!documentId ? (
        <div className="flex flex-1 items-center justify-center p-8">
          <div className="w-full max-w-lg space-y-4">
            <div className="text-center">
              <p className="text-muted-foreground">
                상담할 계약서를 먼저 업로드해주세요
              </p>
            </div>
            <FileUpload onUpload={upload} isUploading={isUploading} />
            {error && (
              <p className="text-sm text-destructive text-center">{error}</p>
            )}
          </div>
        </div>
      ) : (
        <AdviseChat
          messages={messages}
          isLoading={isLoading}
          onSend={sendMessage}
        />
      )}
    </div>
  );
}
