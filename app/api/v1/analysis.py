"""분석 API — Review 그래프 호출."""

import time
import logging

from fastapi import APIRouter, HTTPException

from app.graphs.review_graph import review_graph
from app.models.analysis import ReviewRequest, ReviewResponse
from app.utils.db_client import fetchrow

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/review", response_model=ReviewResponse)
async def review_document(request: ReviewRequest):
    """계약서 분석 (Review 모드).

    LangGraph Review 서브그래프를 실행하여 위험 조항을 분석한다.
    """
    start_time = time.time()

    # 문서 조회
    doc = await fetchrow(
        "SELECT id, raw_text, doc_type, language FROM documents WHERE id = $1",
        str(request.document_id),
    )
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    if not doc["raw_text"]:
        raise HTTPException(status_code=400, detail="문서 텍스트가 파싱되지 않았습니다.")

    # Review 그래프 실행
    try:
        result = await review_graph.ainvoke({
            "document_id": str(request.document_id),
            "raw_text": doc["raw_text"],
            "perspective": request.perspective,
            "focus_areas": request.focus_areas,
            "language": doc.get("language", "ko"),
            "attempt": 0,
            "max_retries": 2,
            "feedback": [],
            "clause_analyses": [],
        })
    except Exception as e:
        logger.error(f"Review 그래프 실행 실패: {e}")
        return ReviewResponse(status="error", error=str(e))

    # 응답 구성
    if result.get("security_status") == "blocked":
        return ReviewResponse(
            status="blocked",
            error="보안 스캔에서 위험 요소가 탐지되어 분석이 차단되었습니다.",
        )

    response_data = result.get("response")
    if response_data:
        elapsed = int((time.time() - start_time) * 1000)
        response_data["processing_time_ms"] = elapsed
        # findings가 RiskFinding 스키마에 맞도록 필수 필드 보충
        sanitized_findings = []
        for f in response_data.get("findings", []):
            sanitized_findings.append({
                "severity": f.get("severity", "info"),
                "category": f.get("category", "unknown"),
                "title": f.get("title", ""),
                "description": f.get("description", ""),
                "original_text": f.get("original_text", ""),
                "suggested_text": f.get("suggested_text"),
                "suggestion_reason": f.get("suggestion_reason"),
                "related_law": f.get("related_law"),
                "precedent_refs": f.get("precedent_refs", []),
                "confidence_score": f.get("confidence_score", 0.0),
            })
        response_data["findings"] = sanitized_findings
        return ReviewResponse(status="completed", analysis=response_data)

    # 검증 실패해도 부분 결과 반환
    elapsed = int((time.time() - start_time) * 1000)
    partial = {
        "document_id": str(request.document_id),
        "overall_risk_score": result.get("overall_risk_score", 0.0),
        "confidence": result.get("confidence", 0.0),
        "risk_summary": result.get("risk_summary", "분석이 완료되었으나 검증을 통과하지 못했습니다."),
        "findings": [],
        "validation": result.get("validation_result"),
        "warnings": ["자동 검증을 통과하지 못했습니다. 결과를 참고용으로만 활용하세요."],
        "processing_time_ms": elapsed,
    }
    # merged_findings가 있으면 포함
    for f in result.get("merged_findings", []):
        partial["findings"].append({
            "severity": f.get("severity", "info"),
            "category": f.get("category", "unknown"),
            "title": f.get("title", ""),
            "description": f.get("description", ""),
            "original_text": f.get("original_text", ""),
            "suggested_text": f.get("suggested_text"),
            "suggestion_reason": f.get("suggestion_reason"),
            "related_law": f.get("related_law"),
            "precedent_refs": f.get("precedent_refs", []),
            "confidence_score": f.get("confidence_score", 0.0),
        })
    return ReviewResponse(status="completed", analysis=partial)
