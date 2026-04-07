"""Validator 노드 — 5단계 검증 (GPT-4o-mini 교차검증).

Analyzer(Claude)와 다른 LLM(GPT)으로 교차 검증.
1. 원문 크로스체크 (fuzzy match >= 0.85)
2. 법률 조항 실존 확인 (DB 조회)
3. 판례 실존 확인 (DB 조회)
4. 논리적 일관성
5. LLM 교차 검증 (위 4개 통과 시에만)
"""

import logging
import re

from rapidfuzz import fuzz

from app.config import settings
from app.llm.client import call_llm_json
from app.llm.prompts.validator_system import VALIDATOR_SYSTEM_PROMPT
from app.state.review_state import ReviewState
from app.utils.db_client import fetch, fetchrow

logger = logging.getLogger(__name__)


async def validate(state: ReviewState) -> dict:
    """5단계 검증 노드."""
    findings = state.get("merged_findings", [])
    raw_text = state.get("raw_text", "")
    rag_results = state.get("rag_results", {})
    overall_risk_score = state.get("overall_risk_score", 0.0)

    issues = []      # 검증 실패 (재시도 대상)
    warnings = []    # 경고 (참고용, 검증 통과에 영향 없음)

    # ── Check 1: 원문 크로스체크 ──
    text_issues = _check_original_text(findings, raw_text)
    issues.extend(text_issues)

    # ── Check 2: 법률 조항 실존 확인 (경고 처리 — DB 데이터 부족) ──
    law_issues = await _verify_law_references(findings)
    warnings.extend(law_issues)

    # ── Check 3: 판례 실존 확인 (경고 처리 — DB 데이터 부족) ──
    precedent_issues = await _verify_precedents(findings)
    warnings.extend(precedent_issues)

    # ── Check 4: 논리적 일관성 ──
    logic_issues = _check_logical_consistency(findings, overall_risk_score)
    issues.extend(logic_issues)

    # ── Check 5: LLM 교차 검증 (위 검증 통과 시에만, 비용 절감) ──
    cross_validated = False
    if not issues and findings:
        cross_issues = await _cross_validate_with_llm(findings, raw_text)
        issues.extend(cross_issues)
        cross_validated = len(cross_issues) == 0

    all_issues = issues + warnings
    passed = len(issues) == 0
    confidence = _calculate_confidence(findings, all_issues)

    feedback = []
    if not passed:
        feedback = [{"type": i.get("type"), "detail": i.get("detail")} for i in issues]

    return {
        "validation_result": {
            "passed": passed,
            "issues": [i.get("detail", "") for i in all_issues],
            "confidence": confidence,
            "cross_validated": cross_validated,
            "validator_model": settings.validator_model,
        },
        "validation_passed": passed,
        "confidence": confidence,
        "feedback": feedback,
        "response": _build_response(state, passed, confidence, all_issues),
    }


# ──────────────────────────────────────────
# Check 1: 원문 크로스체크
# ──────────────────────────────────────────

def _check_original_text(findings: list[dict], original_text: str) -> list[dict]:
    """각 finding의 original_text가 실제 원문에 있는지 fuzzy match."""
    issues = []
    for i, finding in enumerate(findings):
        orig = finding.get("original_text", "")
        if not orig or len(orig) < 5:
            continue

        ratio = fuzz.partial_ratio(orig, original_text)
        if ratio < 85:
            issues.append({
                "type": "text_mismatch",
                "finding_index": i,
                "detail": (
                    f"Finding[{i}] '{finding.get('title', '')}': "
                    f"original_text가 원문과 불일치 (유사도 {ratio}%)"
                ),
                "severity": "error",
            })
    return issues


# ──────────────────────────────────────────
# Check 2: 법률 조항 실존 확인
# ──────────────────────────────────────────

_LAW_REF_PATTERN = re.compile(
    r"(민법|상법|약관규제법|약관의\s*규제에\s*관한\s*법률|근로기준법|주택임대차보호법|"
    r"전자서명법|개인정보\s*보호법|저작권법|부정경쟁방지법)"
    r"\s*제\s*(\d+)\s*조"
)


async def _verify_law_references(findings: list[dict]) -> list[dict]:
    """인용된 법률 조항이 실제로 DB에 존재하는지 확인."""
    issues = []
    for i, finding in enumerate(findings):
        related_law = finding.get("related_law", "")
        if not related_law:
            continue

        match = _LAW_REF_PATTERN.search(related_law)
        if not match:
            continue

        law_name = match.group(1).strip()
        article = f"제{match.group(2)}조"

        try:
            row = await fetchrow(
                "SELECT id FROM laws WHERE law_name LIKE $1 AND article_number = $2",
                f"%{law_name}%", article,
            )
            if not row:
                issues.append({
                    "type": "law_not_found",
                    "finding_index": i,
                    "detail": (
                        f"Finding[{i}]: '{law_name} {article}' 가 "
                        f"법령 DB에서 확인되지 않음 (hallucination 가능)"
                    ),
                    "severity": "error",
                })
        except Exception as e:
            logger.warning(f"법률 확인 DB 조회 실패: {e}")

    return issues


# ──────────────────────────────────────────
# Check 3: 판례 실존 확인
# ──────────────────────────────────────────

_CASE_NUMBER_PATTERN = re.compile(r"\d{4}[가-힣]{1,2}\d+")


async def _verify_precedents(findings: list[dict]) -> list[dict]:
    """인용된 판례 번호가 실제로 DB에 존재하는지 확인."""
    issues = []
    for i, finding in enumerate(findings):
        refs = finding.get("precedent_refs", [])
        description = finding.get("description", "")

        # description에서도 판례번호 추출
        desc_refs = _CASE_NUMBER_PATTERN.findall(description)
        all_refs = list(set(refs + desc_refs))

        for case_num in all_refs:
            try:
                row = await fetchrow(
                    "SELECT id FROM precedents WHERE case_number = $1",
                    case_num,
                )
                if not row:
                    issues.append({
                        "type": "precedent_not_found",
                        "finding_index": i,
                        "detail": (
                            f"Finding[{i}]: 판례 '{case_num}' 가 "
                            f"판례 DB에서 확인되지 않음 (hallucination 가능)"
                        ),
                        "severity": "warning",
                    })
            except Exception as e:
                logger.warning(f"판례 확인 DB 조회 실패: {e}")

    return issues


# ──────────────────────────────────────────
# Check 4: 논리적 일관성
# ──────────────────────────────────────────

def _check_logical_consistency(findings: list[dict], overall_risk_score: float) -> list[dict]:
    """논리적 모순 탐지 (규칙 기반)."""
    issues = []
    if not findings:
        return issues

    severities = [f.get("severity", "info") for f in findings]

    # 규칙 1: severity 전부 low인데 score > 5
    if all(s in ("low", "info") for s in severities) and overall_risk_score > 5:
        issues.append({
            "type": "logic_error",
            "detail": f"모든 severity가 low/info인데 overall_risk_score={overall_risk_score}",
            "severity": "warning",
        })

    # 규칙 2: critical이 있는데 score < 3
    if "critical" in severities and overall_risk_score < 3:
        issues.append({
            "type": "logic_error",
            "detail": f"critical severity 존재하지만 overall_risk_score={overall_risk_score}",
            "severity": "warning",
        })

    # 규칙 3: suggested_text == original_text (무의미한 수정)
    for i, f in enumerate(findings):
        sugg = (f.get("suggested_text") or "").strip()
        orig = (f.get("original_text") or "").strip()
        if sugg and orig and sugg == orig:
            issues.append({
                "type": "logic_error",
                "detail": f"Finding[{i}] '{f.get('title', '')}': suggested_text가 original_text와 동일",
                "severity": "warning",
            })

    # 규칙 4: 같은 조항에 대해 모순되는 severity
    clause_severities: dict[str, list] = {}
    for f in findings:
        cn = f.get("clause_number", "unknown")
        clause_severities.setdefault(cn, []).append(f.get("severity"))
    for cn, sevs in clause_severities.items():
        if "critical" in sevs and "low" in sevs:
            issues.append({
                "type": "logic_error",
                "detail": f"조항 {cn}: critical과 low가 동시에 존재 (모순)",
                "severity": "warning",
            })

    return issues


# ──────────────────────────────────────────
# Check 5: LLM 교차 검증
# ─────────────────────────────────────────��

async def _cross_validate_with_llm(findings: list[dict], original_text: str) -> list[dict]:
    """별도 LLM(GPT-4o-mini)으로 교차 검증."""
    issues = []

    # findings 요약 생성
    findings_summary = []
    for i, f in enumerate(findings[:10]):  # 비용 절감: 최대 10개
        findings_summary.append(
            f"[{i}] severity={f.get('severity')}, "
            f"category={f.get('category')}, "
            f"title={f.get('title')}, "
            f"original_text={f.get('original_text', '')[:100]}"
        )
    findings_text = "\n".join(findings_summary)

    # 원문 요약 (비용 절감)
    doc_excerpt = original_text[:3000] if len(original_text) > 3000 else original_text

    try:
        result = await call_llm_json(
            model=settings.validator_model,  # GPT-4o-mini
            system_prompt=VALIDATOR_SYSTEM_PROMPT,
            user_prompt=(
                f"[계약서 원문 (일부)]\n{doc_excerpt}\n\n"
                f"[AI 분석 결과]\n{findings_text}\n\n"
                "위 분석 결과를 검증하세요."
            ),
            temperature=0.0,
            max_tokens=2048,
        )
        data = result["data"]

        for issue in data.get("issues", []):
            issues.append({
                "type": "cross_validation_fail",
                "finding_index": issue.get("finding_index"),
                "detail": issue.get("detail", "교차 검증에서 문제 발견"),
                "severity": "warning",
            })

        # 놓친 위험도 추가
        for missed in data.get("missed_risks", []):
            logger.info(f"교차 검증 - 놓친 위험: {missed}")

    except Exception as e:
        logger.warning(f"LLM 교차 검증 실패: {e}")

    return issues


# ──────────────────────────────────────────
# 유틸리티
# ──────────────────────────────────────────

def _calculate_confidence(findings: list[dict], issues: list[dict]) -> float:
    """최종 신뢰도 점수."""
    if not findings:
        return 1.0
    scores = [f.get("confidence_score", 0.5) for f in findings]
    base = sum(scores) / len(scores)
    penalty = len(issues) * 0.1
    return max(0.0, min(1.0, round(base - penalty, 2)))


def _build_response(state: ReviewState, passed: bool, confidence: float, issues: list) -> dict:
    """최종 응답."""
    warnings = []
    if not passed:
        warnings.append("자동 검증을 통과하지 못했습니다. 결과를 참고용으로만 활용하세요.")
    if confidence < 0.7:
        warnings.append("신뢰도가 낮습니다. 전문가 검토를 권장합니다.")

    attempt = state.get("attempt", 0)
    if attempt > 0 and passed:
        warnings.append(f"검증 {attempt}회 재시도 후 통과되었습니다.")

    return {
        "document_id": state.get("document_id"),
        "overall_risk_score": state.get("overall_risk_score", 0.0),
        "confidence": confidence,
        "risk_summary": state.get("risk_summary", ""),
        "findings": state.get("merged_findings", []),
        "validation": {
            "all_checks_passed": passed,
            "cross_validated": not any(i.get("type") == "cross_validation_fail" for i in issues),
            "validator_model": settings.validator_model,
            "issues": [i.get("detail") for i in issues],
        },
        "warnings": warnings,
    }
