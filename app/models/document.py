"""문서 관련 Pydantic 모델."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ClauseSchema(BaseModel):
    """조항 스키마."""

    id: UUID | None = None
    clause_number: str | None = None  # "제1조", "Article 1"
    title: str | None = None  # "(목적)", "Purpose"
    content: str
    page_number: int | None = None
    start_index: int | None = None
    end_index: int | None = None
    clause_type: str | None = None  # "손해배상", "해지" 등


class DocumentSchema(BaseModel):
    """문서 스키마."""

    id: UUID | None = None
    file_name: str
    file_type: str = Field(pattern=r"^(pdf|docx)$")
    file_size: int
    raw_text: str | None = None
    clause_count: int = 0
    page_count: int = 0
    language: str = "ko"
    doc_type: str | None = None
    parties: list[str] = Field(default_factory=list)
    status: str = "uploaded"
    created_at: datetime | None = None


class DocumentUploadRequest(BaseModel):
    """문서 업로드 요청."""

    doc_type: str | None = None  # "service_contract", "nda" 등
    language: str = "ko"


class DocumentUploadResponse(BaseModel):
    """문서 업로드 응답."""

    document_id: UUID
    file_name: str
    status: str
    clause_count: int
    page_count: int
    message: str = "문서가 성공적으로 업로드되었습니다."
