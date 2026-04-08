"""Review 서브그래프 State 정의."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class ReviewState(TypedDict, total=False):
    """Review(분석) 파이프라인의 State.

    문서 업로드 → 보안 스캔 → 파싱 → 분석+RAG(병렬) → 병합 → 검증 → 재시도
    """

    # ── 입력 ──
    document_id: str
    raw_text: str
    perspective: str  # "갑" | "을" | "neutral"
    focus_areas: list[str]

    # ── 보안 스캔 ──
    security_result: dict[str, Any] | None
    security_status: str  # "clean" | "suspicious" | "blocked"

    # ── 문서 파싱 ──
    clauses: list[dict[str, Any]]  # 분리된 조항 목록
    doc_type: str | None  # LLM 분류 결과 코드 (예: "sales", "lease", "franchise" 등)
    doc_type_label: str | None  # 한국어 레이블 (예: "부동산 매매 계약서")
    parties: list[str]  # 당사자 목록
    language: str  # "ko" | "en"

    # ── 분석 결과 (Annotated로 병렬 결과 누적) ──
    clause_analyses: Annotated[list[dict[str, Any]], operator.add]  # 조항별 분석
    doc_level_analysis: dict[str, Any] | None  # 문서 전체 분석
    rag_results: dict[str, Any] | None  # RAG 검색 결과 (법령/판례/표준조항)

    # ── 병합 결과 ──
    merged_findings: list[dict[str, Any]]  # Analyzer + RAG 결과 병합
    overall_risk_score: float | None
    risk_summary: str | None

    # ── 검증 ──
    validation_result: dict[str, Any] | None
    validation_passed: bool
    confidence: float | None

    # ── 재시도 ──
    attempt: int  # 현재 시도 횟수 (0부터 시작)
    max_retries: int  # 최대 재시도 횟수 (기본 2)
    feedback: list[dict[str, Any]]  # Validator 피드백 (재시도 시 참조)

    # ── 최종 출력 ──
    response: dict[str, Any] | None
    error: str | None
