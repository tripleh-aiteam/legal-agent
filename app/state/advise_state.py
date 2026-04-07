"""Advise 서브그래프 State 정의."""

from __future__ import annotations

from typing import Any, TypedDict


class AdviseState(TypedDict, total=False):
    """Advise(상담) 파이프라인의 State.

    세션 로드 → 관련 조항 추출 → RAG 검색 → 답변 생성 → 세션 업데이트
    """

    # ── 세션 ──
    session_id: str
    document_id: str
    raw_text: str
    clauses: list[dict[str, Any]]  # 문서의 조항 목록

    # ── 사용자 입력 ──
    message: str  # 사용자 질문
    conversation_history: list[dict[str, str]]  # 대화 히스토리

    # ── 조항 매칭 ──
    target_clause: dict[str, Any] | None  # 질문과 관련된 조항
    match_method: str | None  # "explicit" | "keyword" | "context"

    # ── RAG ──
    rag_results: dict[str, Any] | None  # 법률/판례 검색 결과

    # ── 답변 ──
    advice_response: dict[str, Any] | None
    # 응답 구조:
    # {
    #   "judgment": "🔴위험 / 🟡주의 / 🟢안전",
    #   "reason": "구체적 설명",
    #   "legal_basis": {"laws": [...], "precedents": [...]},
    #   "action_suggestion": "행동 제안",
    #   "follow_up_questions": ["질문1", "질문2"],
    #   "disclaimer": "면책 문구"
    # }

    # ── 출력 ──
    response: dict[str, Any] | None
    error: str | None
