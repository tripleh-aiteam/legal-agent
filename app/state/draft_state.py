"""Draft 서브그래프 State 정의."""

from __future__ import annotations

from typing import Any, TypedDict


class DraftState(TypedDict, total=False):
    """Draft(생성) 파이프라인의 State.

    인터뷰(정보수집) → 표준서식 검색 → 계약서 생성 → 자체검증 → 수정 → 출력
    """

    # ── 세션 ──
    session_id: str
    contract_type: str  # "service_contract" | "nda" | "employment" | "lease"

    # ── 인터뷰 ──
    interview_data: dict[str, Any]  # 수집된 정보 {field: value}
    interview_complete: bool  # 필수 정보 수집 완료 여부
    current_question: dict[str, Any] | None  # 현재 질문 (multi-turn)
    pending_fields: list[str]  # 아직 수집하지 못한 필드

    # ── 서식 검색 ──
    template_clauses: list[dict[str, Any]]  # RAG에서 가져온 표준 서식 조항

    # ── 생성 ──
    generated_contract: str | None  # 생성된 계약서 텍스트
    generated_clauses: list[dict[str, Any]]  # 생성된 조항 목록

    # ── 자체 검증 ──
    review_result: dict[str, Any] | None  # Analyzer + Validator 검토 결과
    review_passed: bool

    # ── 재시도 ──
    attempt: int
    max_retries: int  # 기본 2

    # ── 출력 ──
    output_format: str  # "docx" | "pdf"
    output_path: str | None  # 생성된 파일 경로
    response: dict[str, Any] | None
    error: str | None
