"""분석 결과 관련 Pydantic 모델."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RiskFinding(BaseModel):
    """위험 조항 분석 결과."""

    id: UUID | None = None
    clause_id: UUID | None = None
    severity: str = Field(pattern=r"^(critical|high|medium|low|info)$")
    category: str  # unlimited_liability, unfair_termination, etc.
    title: str
    description: str
    original_text: str
    suggested_text: str | None = None
    suggestion_reason: str | None = None
    related_law: str | None = None  # "민법 제393조"
    precedent_refs: list[str] = Field(default_factory=list)  # ["2023다54321"]
    confidence_score: float = Field(ge=0.0, le=1.0, default=0.0)


class AnalysisResult(BaseModel):
    """전체 분석 결과."""

    id: UUID | None = None
    document_id: UUID
    analysis_type: str = "full_review"
    overall_risk_score: float = Field(ge=0.0, le=10.0)
    risk_summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    findings: list[RiskFinding] = Field(default_factory=list)
    validation: ValidationSummary | None = None
    warnings: list[str] = Field(default_factory=list)
    llm_model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0
    processing_time_ms: int = 0
    created_at: datetime | None = None


class ValidationSummary(BaseModel):
    """검증 요약."""

    all_checks_passed: bool
    cross_validated: bool = False
    validator_model: str | None = None
    issues: list[str] = Field(default_factory=list)


class ReviewRequest(BaseModel):
    """분석 요청."""

    document_id: UUID
    perspective: str = "neutral"  # "갑" | "을" | "neutral"
    focus_areas: list[str] = Field(default_factory=list)
    llm_preference: str | None = None  # 선호 LLM 모델


class ReviewResponse(BaseModel):
    """분석 응답."""

    status: str  # "completed" | "blocked" | "error"
    analysis: AnalysisResult | None = None
    error: str | None = None
