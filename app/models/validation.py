"""검증 결과 관련 Pydantic 모델."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ValidationIssue(BaseModel):
    """검증에서 발견된 문제."""

    type: str  # "text_mismatch" | "law_not_found" | "precedent_not_found" | "logic_error" | "cross_validation_fail"
    finding_id: str | None = None
    detail: str
    severity: str = "warning"  # "error" | "warning"


class ValidationResult(BaseModel):
    """Validator 검증 결과."""

    passed: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)

    # 각 단계별 결과
    text_check_passed: bool = True
    law_check_passed: bool = True
    precedent_check_passed: bool = True
    logic_check_passed: bool = True
    cross_validation_passed: bool | None = None  # None = 미실행

    validator_model: str | None = None
