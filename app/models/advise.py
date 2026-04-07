"""Advise(상담) 관련 Pydantic 모델."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AdviseRequest(BaseModel):
    """상담 요청."""

    session_id: str | None = None  # 기존 세션 ID (없으면 새로 생성)
    document_id: UUID
    message: str


class AdviceContent(BaseModel):
    """상담 응답 내용."""

    judgment: str  # "🔴위험" | "🟡주의" | "🟢안전"
    reason: str
    legal_basis: dict[str, Any] = Field(default_factory=dict)
    # {"laws": ["민법 제393조 ..."], "precedents": ["2023다54321 ..."]}
    action_suggestion: str
    follow_up_questions: list[str] = Field(default_factory=list, max_length=2)
    disclaimer: str = "본 정보는 AI가 제공하는 참고 정보이며, 법률 자문이 아닙니다. 중요한 법률적 결정은 반드시 변호사와 상담하세요."


class AdviseResponse(BaseModel):
    """상담 응답."""

    session_id: str
    status: str  # "answered" | "error"
    advice: AdviceContent | None = None
    matched_clause: dict[str, Any] | None = None  # 매칭된 조항 정보
    error: str | None = None
