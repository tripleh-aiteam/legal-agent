"""Orchestrator 메인 그래프 State 정의."""

from __future__ import annotations

from typing import Any, TypedDict


class OrchestratorState(TypedDict, total=False):
    """메인 Orchestrator 그래프의 State.

    사용자 요청을 받아 모드를 분류하고, 해당 서브그래프로 라우팅한다.
    """

    # ── 입력 ──
    request_type: str  # 힌트: "review" | "draft" | "advise" (명시적 지정 시)
    document_id: str | None
    raw_text: str | None  # 파싱된 문서 텍스트
    file_path: str | None  # 업로드 파일 경로
    file_type: str | None  # "pdf" | "docx"
    message: str | None  # advise 모드: 사용자 질문
    session_id: str | None  # advise/draft 세션 ID
    perspective: str  # "갑" | "을" | "neutral"
    focus_areas: list[str]  # 집중 분석 영역

    # ── 분류 결과 ──
    intent: str  # classify_intent 결과: "review" | "draft" | "advise"

    # ── 보안 ──
    security_status: str  # "clean" | "suspicious" | "blocked"

    # ── 최종 출력 ──
    response: dict[str, Any] | None
    error: str | None
