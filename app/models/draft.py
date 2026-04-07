"""Draft(생성) 관련 Pydantic 모델."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class InterviewQuestion(BaseModel):
    """인터뷰 질문."""

    field: str
    question: str
    sub_questions: list[str] = Field(default_factory=list)
    examples: str | None = None
    default: str | None = None
    warning: str | None = None
    is_required: bool = True


class DraftStartRequest(BaseModel):
    """계약서 생성 시작 요청."""

    user_input: str  # 사용자 초기 입력 (예: "프리랜서 용역계약 만들어줘")


class DraftContinueRequest(BaseModel):
    """인터뷰 진행 요청."""

    session_id: str
    answer: str  # 사용자 답변


class DraftGenerateRequest(BaseModel):
    """계약서 생성 요청."""

    session_id: str
    output_format: str = "docx"  # "docx" | "pdf"


class DraftResponse(BaseModel):
    """Draft 응답."""

    session_id: str
    status: str  # "interviewing" | "generating" | "reviewing" | "completed" | "error"
    question: InterviewQuestion | None = None  # 다음 질문
    progress: dict[str, Any] | None = None  # 진행 상태
    contract_text: str | None = None  # 생성된 계약서
    review_summary: dict[str, Any] | None = None  # 자체 검토 결과
    output_path: str | None = None
    message: str | None = None
