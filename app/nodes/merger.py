"""merge_results 노드 — Analyzer + RAG 결과 병합.

분석 결과에 법률 근거를 연결하고, 최종 findings를 생성한다.
"""

from app.state.review_state import ReviewState


def merge_results(state: ReviewState) -> dict:
    """Analyzer 결과와 RAG 결과를 병합하는 노드.

    각 finding에 관련 법률/판례 근거를 매칭한다.
    """
    clause_analyses = state.get("clause_analyses", [])
    doc_level_analysis = state.get("doc_level_analysis", {})
    rag_results = state.get("rag_results", {})

    merged_findings = []

    # 각 조항별 분석 결과에서 findings 추출
    for analysis in clause_analyses:
        findings = analysis.get("findings", [])
        for finding in findings:
            # RAG 결과에서 관련 법률/판례 매칭
            enriched = _enrich_finding_with_rag(finding, rag_results)
            merged_findings.append(enriched)

    # 문서 전체 분석에서 누락 조항 등 추가
    missing = doc_level_analysis.get("missing_clauses", [])
    for item in missing:
        merged_findings.append({
            "severity": "info",
            "category": "missing_clause",
            "title": f"누락 조항: {item}",
            "description": f"표준 계약서에 포함되는 '{item}' 조항이 없습니다.",
            "original_text": "",
            "confidence_score": 0.8,
        })

    # 위험도 종합 점수 산출
    overall_score = _calculate_overall_risk_score(merged_findings)
    risk_summary = _generate_risk_summary(merged_findings, overall_score)

    return {
        "merged_findings": merged_findings,
        "overall_risk_score": overall_score,
        "risk_summary": risk_summary,
    }


def _enrich_finding_with_rag(finding: dict, rag_results: dict) -> dict:
    """finding에 RAG 근거를 연결."""
    # TODO: Phase 5에서 키워드/의미 매칭으로 관련 법률/판례 연결
    return finding


def _calculate_overall_risk_score(findings: list[dict]) -> float:
    """위험도 종합 점수 산출 (0~10)."""
    if not findings:
        return 0.0

    severity_weights = {
        "critical": 10,
        "high": 7,
        "medium": 4,
        "low": 1,
        "info": 0,
    }

    total_weight = sum(severity_weights.get(f.get("severity", "info"), 0) for f in findings)
    max_possible = len(findings) * 10

    if max_possible == 0:
        return 0.0

    return min(10.0, round((total_weight / max_possible) * 10, 1))


def _generate_risk_summary(findings: list[dict], score: float) -> str:
    """위험도 요약 생성."""
    critical_count = sum(1 for f in findings if f.get("severity") == "critical")
    high_count = sum(1 for f in findings if f.get("severity") == "high")

    if score >= 7:
        level = "높음"
    elif score >= 4:
        level = "보통"
    else:
        level = "낮음"

    return (
        f"전체 위험도: {level} ({score}/10). "
        f"심각 {critical_count}건, 높음 {high_count}건, 총 {len(findings)}건의 위험 요소 발견."
    )
