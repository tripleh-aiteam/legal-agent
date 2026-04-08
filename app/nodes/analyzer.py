"""Analyzer 노드 — 계약서 위험 조항 분석 (Claude Sonnet).

조항별 독립 분석 + 문서 전체 균형성 평가 + 누락 표준 조항 탐지.
"""

import asyncio
import logging
from typing import Any

from app.config import settings
from app.llm.client import call_llm_json
from app.llm.prompts.analyzer_system import ANALYZER_SYSTEM_PROMPT
from app.state.review_state import ReviewState

logger = logging.getLogger(__name__)

RISK_CATEGORIES = {
    "unlimited_liability": {"severity": "critical", "label": "무제한 손해배상"},
    "unfair_termination": {"severity": "high", "label": "불공정 해지"},
    "auto_renewal_trap": {"severity": "high", "label": "자동갱신 함정"},
    "ip_ownership_risk": {"severity": "high", "label": "지재권 리스크"},
    "non_compete_excessive": {"severity": "medium", "label": "과도한 경업금지"},
    "confidentiality_onesided": {"severity": "medium", "label": "편면적 비밀유지"},
    "payment_risk": {"severity": "medium", "label": "대금 지급 리스크"},
    "jurisdiction_risk": {"severity": "medium", "label": "관할권 리스크"},
    "indemnification_broad": {"severity": "high", "label": "면책 범위 과다"},
    "missing_clause": {"severity": "info", "label": "누락 조항"},
}

# 계약 유형별 필수 조항 체크리스트
REQUIRED_CLAUSES_BY_TYPE = {
    "sales": ["매매대금", "소유권이전", "계약금", "중도금", "잔금", "하자담보", "해제", "위약금"],
    "service_contract": ["손해배상", "해지", "비밀유지", "지식재산권", "대금지급", "분쟁해결", "납품/검수"],
    "nda": ["비밀정보정의", "비밀유지의무", "기간", "예외", "반환/파기"],
    "employment": ["근로조건", "임금", "근무시간", "해고", "비밀유지"],
    "lease": ["보증금", "차임", "수선의무", "해지", "원상회복", "보증금반환"],
}


async def analyze_clauses(state: ReviewState) -> dict:
    """조항별 분석 + 문서 전체 분석. RAG 결과를 법률 근거로 활용."""
    clauses = state.get("clauses", [])
    perspective = state.get("perspective", "neutral")
    raw_text = state.get("raw_text", "")
    doc_type = state.get("doc_type")
    parties = state.get("parties", [])
    rag_results = state.get("rag_results") or {}

    if not clauses:
        return {"clause_analyses": [], "doc_level_analysis": None}

    # RAG 결과를 참고자료 텍스트로 변환
    rag_context = _build_rag_context(rag_results)

    # 전체 문서 요약 (조항 분석 시 맥락으로 제공)
    doc_summary = _build_doc_summary(clauses, doc_type, parties)

    # 조항별 분석 — 첫 1회로 프롬프트 캐시 워밍업 후 나머지 병렬
    first = await _analyze_single_clause(
        clauses[0], doc_summary, perspective, doc_type, rag_context=rag_context,
    )
    if len(clauses) > 1:
        rest = await asyncio.gather(*(
            _analyze_single_clause(
                clause, doc_summary, perspective, doc_type, rag_context=rag_context,
            )
            for clause in clauses[1:]
        ))
        clause_analyses = [first, *rest]
    else:
        clause_analyses = [first]

    # 문서 전체 분석
    doc_level = await _analyze_document_level(clauses, clause_analyses, perspective, doc_type)

    return {
        "clause_analyses": list(clause_analyses),
        "doc_level_analysis": doc_level,
    }


async def retry_with_feedback(state: ReviewState) -> dict:
    """Validator 피드백 반영 — 문제 조항만 재분석."""
    feedback = state.get("feedback", [])
    attempt = state.get("attempt", 0)
    clauses = state.get("clauses", [])
    perspective = state.get("perspective", "neutral")
    doc_type = state.get("doc_type")
    existing_analyses = state.get("clause_analyses", [])

    if not feedback:
        return {"attempt": attempt + 1}

    # 피드백에서 문제가 된 finding_index → 해당 조항 번호 추출
    merged_findings = state.get("merged_findings", [])
    problem_clause_numbers = set()
    for fb in feedback:
        idx = fb.get("finding_index")
        if idx is not None and idx < len(merged_findings):
            cn = merged_findings[idx].get("clause_number", "")
            if cn:
                problem_clause_numbers.add(cn)

    # finding_index가 없는 피드백이 있으면 detail에서 조항 번호 매칭 시도
    if not problem_clause_numbers:
        for fb in feedback:
            detail = fb.get("detail", "")
            for clause in clauses:
                cn = clause.get("clause_number", "")
                if cn and cn in detail:
                    problem_clause_numbers.add(cn)

    # 그래도 못 찾으면 전체 재분석 (폴백)
    if not problem_clause_numbers:
        problem_clause_numbers = {c.get("clause_number", "") for c in clauses}

    feedback_text = "\n".join(f"- {fb.get('detail', '')}" for fb in feedback)
    doc_summary = _build_doc_summary(clauses, doc_type, state.get("parties", []))

    # 문제 조항만 재분석, 나머지는 기존 결과 유지
    reanalyze_clauses = [
        c for c in clauses if c.get("clause_number", "") in problem_clause_numbers
    ]

    logger.info(
        f"재분석 대상: {len(reanalyze_clauses)}/{len(clauses)}개 조항 "
        f"({problem_clause_numbers})"
    )

    rag_context = _build_rag_context(state.get("rag_results") or {})

    reanalyzed = await asyncio.gather(*(
        _analyze_single_clause(
            clause, doc_summary, perspective, doc_type,
            feedback=feedback_text, rag_context=rag_context,
        )
        for clause in reanalyze_clauses
    ))

    # 기존 결과에 재분석 결과를 병합
    reanalyzed_map = {r["clause_number"]: r for r in reanalyzed}
    clause_analyses = [
        reanalyzed_map.get(a["clause_number"], a)
        for a in existing_analyses
    ]

    doc_level = await _analyze_document_level(clauses, clause_analyses, perspective, doc_type)

    return {
        "clause_analyses": clause_analyses,
        "doc_level_analysis": doc_level,
        "attempt": attempt + 1,
    }


def _build_rag_context(rag_results: dict) -> str:
    """RAG 검색 결과를 Analyzer에 제공할 참고자료 텍스트로 변환."""
    parts = []

    # 법령
    laws = rag_results.get("laws", [])
    if laws:
        parts.append("## 관련 법령")
        for law in laws:
            parts.append(
                f"- {law.get('law_name', '')} {law.get('article_number', '')}"
                f" {law.get('article_title', '')}\n"
                f"  {law.get('content', '')[:300]}"
            )

    # 판례
    precedents = rag_results.get("precedents", [])
    if precedents:
        parts.append("\n## 관련 판례")
        for p in precedents:
            parts.append(
                f"- {p.get('court', '')} {p.get('case_number', '')}: "
                f"{p.get('title', '')}\n"
                f"  요지: {p.get('summary', '')[:200]}"
            )

    # 표준 계약서 조항
    standards = rag_results.get("standards", [])
    if standards:
        parts.append("\n## 표준 계약서 조항")
        for s in standards:
            mandatory = " (필수)" if s.get("is_mandatory") else ""
            parts.append(
                f"- [{s.get('contract_type', '')}] {s.get('clause_type', '')}{mandatory}\n"
                f"  {s.get('standard_text', '')[:300]}"
            )

    return "\n".join(parts) if parts else ""


def _build_doc_summary(clauses: list, doc_type: str | None, parties: list) -> str:
    """문서 요약 생성 (조항 분석 시 맥락으로 제공)."""
    parts = []
    if doc_type:
        parts.append(f"문서유형: {doc_type}")
    if parties:
        parts.append(f"당사자: {', '.join(parties)}")
    parts.append(f"총 {len(clauses)}개 조항")
    clause_list = "\n".join(
        f"  {c.get('clause_number', '?')} {c.get('title', '')}"
        for c in clauses
    )
    parts.append(f"조항 목록:\n{clause_list}")
    return "\n".join(parts)


async def _analyze_single_clause(
    clause: dict,
    doc_summary: str,
    perspective: str,
    doc_type: str | None,
    feedback: str | None = None,
    rag_context: str | None = None,
) -> dict:
    """개별 조항을 LLM으로 분석. RAG 검색 결과를 법률 근거로 제공."""
    content = clause.get("content", "")
    clause_number = clause.get("clause_number", "")
    title = clause.get("title", "")

    system_prompt = ANALYZER_SYSTEM_PROMPT.replace("{perspective}", perspective)

    user_parts = [
        f"[문서 정보]\n{doc_summary}",
        f"\n[분석 대상 조항]\n{clause_number} {title}\n{content}",
        f"\n[분석 관점]: {perspective}",
    ]
    if doc_type:
        user_parts.append(f"[계약 유형]: {doc_type}")
    if rag_context:
        user_parts.append(
            f"\n[참고 법률 자료 — DB에서 검색된 실제 법령/판례/표준조항입니다. "
            f"분석과 수정 제안 시 반드시 이 자료를 근거로 활용하세요]\n{rag_context}"
        )
    if feedback:
        user_parts.append(
            f"\n[이전 분석 피드백 — 아래 문제를 수정하세요]\n{feedback}"
        )

    user_prompt = "\n".join(user_parts)

    try:
        result = await call_llm_json(
            model=settings.analyzer_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=4096,
        )
        data = result["data"]
        findings = data.get("findings", [])

        return {
            "clause_number": clause_number,
            "title": title,
            "findings": findings,
            "usage": result.get("usage"),
        }
    except Exception as e:
        logger.error(f"조항 분석 실패 ({clause_number}): {e}")
        return {
            "clause_number": clause_number,
            "title": title,
            "findings": [],
            "error": str(e),
        }


async def _analyze_document_level(
    clauses: list, clause_analyses: list, perspective: str, doc_type: str | None
) -> dict:
    """문서 전체 수준 분석: 균형성 + 누락 조항 탐지."""

    # 전체 findings 수집
    all_findings = []
    for analysis in clause_analyses:
        all_findings.extend(analysis.get("findings", []))

    # 누락 조항 체크 (규칙 기반)
    missing_clauses = _check_missing_clauses(clauses, doc_type)

    # 갑-을 균형성 LLM 분석
    clauses_text = "\n".join(
        f"{c.get('clause_number', '?')}: {c.get('content', '')[:200]}"
        for c in clauses[:10]
    )

    try:
        balance_result = await call_llm_json(
            model=settings.classifier_model,  # 저렴한 모델로 충분
            system_prompt="계약서의 갑-을 균형성을 분석하세요. JSON으로 응답: {\"balance\": \"balanced|gap_favorable|eul_favorable\", \"reason\": \"설명\", \"score\": 0~10}",
            user_prompt=f"관점: {perspective}\n\n조항 요약:\n{clauses_text}",
            max_tokens=512,
        )
        balance = balance_result["data"]
    except Exception:
        balance = {"balance": "unknown", "reason": "분석 실패", "score": 5}

    # 위험도 종합
    severity_weights = {"critical": 10, "high": 7, "medium": 4, "low": 1, "info": 0}
    total = sum(severity_weights.get(f.get("severity", "info"), 0) for f in all_findings)
    max_possible = max(len(all_findings) * 10, 1)
    overall_score = min(10.0, round((total / max_possible) * 10, 1))

    return {
        "balance_assessment": balance,
        "missing_clauses": missing_clauses,
        "overall_risk_score": overall_score,
        "total_findings": len(all_findings),
    }


def _check_missing_clauses(clauses: list, doc_type: str | None) -> list[str]:
    """계약 유형별 필수 조항 누락 체크."""
    if not doc_type or doc_type not in REQUIRED_CLAUSES_BY_TYPE:
        return []

    required = REQUIRED_CLAUSES_BY_TYPE[doc_type]
    all_content = " ".join(c.get("content", "") + " " + (c.get("title") or "") for c in clauses)

    missing = []
    for req in required:
        if req not in all_content:
            missing.append(req)

    return missing
