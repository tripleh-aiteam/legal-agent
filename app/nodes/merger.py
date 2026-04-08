"""merge_results 노드 — Analyzer + RAG 결과 병합.

분석 결과에 법률 근거를 연결하고, 최종 findings를 생성한다.
"""

import re

from app.state.review_state import ReviewState


def merge_results(state: ReviewState) -> dict:
    """Analyzer 결과와 RAG 결과를 병합하는 노드.

    각 finding에 관련 법률/판례 근거를 매칭한다.
    """
    clause_analyses = state.get("clause_analyses", [])
    doc_level_analysis = state.get("doc_level_analysis", {})
    rag_results = state.get("rag_results") or {}

    merged_findings = []

    # 각 조항별 분석 결과에서 findings 추출
    for analysis in clause_analyses:
        clause_number = analysis.get("clause_number", "")
        findings = analysis.get("findings", [])
        for finding in findings:
            finding["clause_number"] = finding.get("clause_number", clause_number)
            enriched = _enrich_finding_with_rag(finding, rag_results)
            merged_findings.append(enriched)

    # 문서 전체 분석에서 누락 조항 등 추가
    missing = doc_level_analysis.get("missing_clauses", [])
    for item in missing:
        # 표준 조항이 있으면 참고 텍스트를 함께 제공
        standard_ref = _find_standard_for_missing(item, rag_results.get("standards", []))
        desc = f"표준 계약서에 포함되는 '{item}' 조항이 없습니다."
        if standard_ref:
            desc += f"\n참고 표준 조항: {standard_ref}"
        merged_findings.append({
            "severity": "info",
            "category": "missing_clause",
            "title": f"누락 조항: {item}",
            "description": desc,
            "original_text": "",
            "suggested_text": standard_ref or "",
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
    """finding에 RAG 근거를 연결 — 키워드 매칭으로 법률/판례 검증."""
    related_law = finding.get("related_law", "")
    description = finding.get("description", "")
    match_text = f"{related_law} {description} {finding.get('title', '')}"

    # 법령 매칭: finding이 인용한 법률이 RAG 결과에 있는지 확인
    laws = rag_results.get("laws", [])
    matched_laws = []
    for law in laws:
        law_name = law.get("law_name", "")
        article = law.get("article_number", "")
        if law_name and (law_name in match_text or article in match_text):
            matched_laws.append(law)

    # 판례 매칭
    precedents = rag_results.get("precedents", [])
    matched_precedents = []
    case_nums_in_finding = re.findall(r"\d{4}[가-힣]{1,2}\d+", match_text)
    for p in precedents:
        case_num = p.get("case_number", "")
        if case_num in match_text or case_num in case_nums_in_finding:
            matched_precedents.append(p)

    # 키워드 매칭 안 되면 카테고리 기반 매칭 시도
    if not matched_laws:
        category = finding.get("category", "")
        category_keywords = _category_to_keywords(category)
        for law in laws:
            content = law.get("content", "")
            if any(kw in content for kw in category_keywords):
                matched_laws.append(law)
                break

    # finding에 근거 정보 추가
    finding["rag_law_refs"] = [
        {
            "law_name": l.get("law_name", ""),
            "article_number": l.get("article_number", ""),
            "article_title": l.get("article_title", ""),
            "content": l.get("content", "")[:200],
        }
        for l in matched_laws[:3]
    ]
    finding["rag_precedent_refs"] = [
        {
            "case_number": p.get("case_number", ""),
            "court": p.get("court", ""),
            "title": p.get("title", ""),
            "summary": p.get("summary", "")[:200],
        }
        for p in matched_precedents[:2]
    ]

    # 근거 유무에 따라 confidence 보정
    has_rag_support = bool(matched_laws or matched_precedents)
    base_confidence = finding.get("confidence_score", 0.5)
    if has_rag_support:
        finding["confidence_score"] = min(1.0, base_confidence + 0.1)
        finding["rag_verified"] = True
    else:
        finding["confidence_score"] = max(0.0, base_confidence - 0.15)
        finding["rag_verified"] = False

    return finding


def _category_to_keywords(category: str) -> list[str]:
    """위험 카테고리를 법률 검색 키워드로 변환."""
    mapping = {
        "unlimited_liability": ["손해배상", "배상", "제393조", "제398조"],
        "unfair_termination": ["해지", "해제", "제9조"],
        "auto_renewal_trap": ["갱신", "자동연장"],
        "ip_ownership_risk": ["지식재산", "저작권", "특허"],
        "non_compete_excessive": ["경업금지", "경쟁", "전직"],
        "confidentiality_onesided": ["비밀유지", "기밀"],
        "payment_risk": ["대금", "지급", "보수"],
        "jurisdiction_risk": ["관할", "분쟁", "중재"],
        "indemnification_broad": ["면책", "면제", "제7조"],
    }
    return mapping.get(category, [])


def _find_standard_for_missing(clause_name: str, standards: list) -> str:
    """누락 조항에 대응하는 표준 조항 텍스트를 찾는다."""
    for s in standards:
        clause_type = s.get("clause_type", "")
        if clause_name in clause_type or clause_type in clause_name:
            return s.get("standard_text", "")[:300]
    return ""


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
