"""보안 관련 Pydantic 모델."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SecurityThreat(BaseModel):
    """보안 위협 항목."""

    type: str  # "hidden_text" | "injection" | "homoglyph" | "zero_width" | "bidi" | "encoding"
    severity: str  # "critical" | "high" | "medium" | "low"
    description: str
    location: str | None = None  # 위치 정보 (페이지 번호, 인덱스 등)
    raw_content: str | None = None  # 감지된 원본 내용 (일부)


class SecurityResult(BaseModel):
    """보안 스캔 결과."""

    status: str  # "clean" | "suspicious" | "blocked"
    threat_level: str  # "none" | "low" | "medium" | "high" | "blocked"
    threats: list[SecurityThreat] = Field(default_factory=list)
    scan_time_ms: int = 0


class AuditLog(BaseModel):
    """보안 감사 로그."""

    id: UUID | None = None
    event_type: str  # "document_scan" | "injection_attempt" | "pii_detected" | "output_violation"
    severity: str  # "critical" | "high" | "medium" | "low"
    document_id: UUID | None = None
    user_id: UUID | None = None
    description: str
    raw_payload: dict | None = None
    action_taken: str  # "blocked" | "sanitized" | "logged" | "allowed"
    created_at: datetime | None = None
