"""계약서 생성(Draft) API — Draft 그래프 호출."""

import json
import logging

from fastapi import APIRouter, HTTPException

from app.graphs.draft_graph import draft_graph
from app.models.draft import (
    DraftContinueRequest,
    DraftGenerateRequest,
    DraftResponse,
    DraftStartRequest,
)
from app.nodes.drafter import CONTRACT_TYPE_MAP
from app.utils.db_client import execute, fetchrow

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/start", response_model=DraftResponse)
async def start_draft(request: DraftStartRequest):
    """계약서 생성 시작 — 인터뷰 첫 턴."""
    user_input = request.user_input.strip()

    # 사용자 입력에서 계약 유형 추론
    contract_type = ""
    for keyword, ctype in CONTRACT_TYPE_MAP.items():
        if keyword in user_input:
            contract_type = ctype
            break

    result = await draft_graph.ainvoke({
        "session_id": "",
        "contract_type": contract_type,
        "interview_data": {},
        "interview_complete": False,
        "pending_fields": [],
        "template_clauses": [],
        "attempt": 0,
        "max_retries": 2,
    })

    session_id = result.get("session_id", "")
    pending_fields = result.get("pending_fields", [])

    # 세션을 DB에 저장
    await execute(
        """
        INSERT INTO draft_sessions (id, contract_type, interview_data, interview_complete, pending_fields)
        VALUES ($1::uuid, $2, $3::jsonb, $4, $5::jsonb)
        """,
        session_id,
        contract_type,
        json.dumps(result.get("interview_data", {}), ensure_ascii=False),
        result.get("interview_complete", False),
        json.dumps(pending_fields, ensure_ascii=False),
    )

    resp = result.get("response", {})
    return DraftResponse(
        session_id=session_id,
        status=resp.get("status", "interviewing"),
        question=resp.get("question"),
        message=f"인터뷰를 시작합니다. 계약 유형: {contract_type or '미정'}",
    )


@router.post("/continue", response_model=DraftResponse)
async def continue_draft(request: DraftContinueRequest):
    """인터뷰 진행 — 사용자 답변 처리."""
    session_id = request.session_id

    # DB에서 세션 로드
    session = await fetchrow(
        "SELECT * FROM draft_sessions WHERE id = $1::uuid", session_id
    )
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    row = dict(session)

    # JSONB 값이 문자열로 올 수 있으므로 안전하게 파싱
    raw_interview = row.get("interview_data") or {}
    if isinstance(raw_interview, str):
        raw_interview = json.loads(raw_interview)
    interview_data = dict(raw_interview)

    raw_pending = row.get("pending_fields") or []
    if isinstance(raw_pending, str):
        raw_pending = json.loads(raw_pending)
    pending_fields = list(raw_pending)

    # 현재 필드에 답변 저장 (sub_fields JSON이면 파싱하여 구조화)
    if pending_fields:
        current_field = pending_fields[0]
        answer = request.answer
        try:
            parsed = json.loads(answer)
            if isinstance(parsed, dict):
                # sub_fields에서 온 구조화된 답변
                interview_data[current_field] = parsed
            else:
                interview_data[current_field] = answer
        except (json.JSONDecodeError, TypeError):
            interview_data[current_field] = answer

    # 계약 유형 설정 (첫 질문 답변인 경우)
    contract_type = row.get("contract_type", "")
    if not contract_type and "contract_type" not in interview_data:
        for keyword, ctype in CONTRACT_TYPE_MAP.items():
            if keyword in request.answer:
                contract_type = ctype
                break

    result = await draft_graph.ainvoke({
        "session_id": session_id,
        "contract_type": contract_type or row.get("contract_type", ""),
        "interview_data": interview_data,
        "interview_complete": False,
        "pending_fields": [],
        "template_clauses": [],
        "attempt": 0,
        "max_retries": 2,
    })

    # 세션 업데이트
    await execute(
        """
        UPDATE draft_sessions SET
            interview_data = $1::jsonb,
            contract_type = $2,
            interview_complete = $3,
            pending_fields = $4::jsonb,
            updated_at = NOW()
        WHERE id = $5::uuid
        """,
        json.dumps(result.get("interview_data", {}), ensure_ascii=False),
        result.get("contract_type", contract_type),
        result.get("interview_complete", False),
        json.dumps(result.get("pending_fields", []), ensure_ascii=False),
        session_id,
    )

    resp = result.get("response", {})
    return DraftResponse(
        session_id=session_id,
        status=resp.get("status", "interviewing"),
        question=resp.get("question"),
        progress=resp.get("progress"),
        contract_text=resp.get("contract_text"),
        review_summary=resp.get("review_summary"),
        output_path=resp.get("output_path"),
    )


@router.post("/generate", response_model=DraftResponse)
async def generate_draft(request: DraftGenerateRequest):
    """계약서 생성 — 인터뷰 완료 후 생성 실행."""
    session_id = request.session_id

    session = await fetchrow(
        "SELECT * FROM draft_sessions WHERE id = $1::uuid", session_id
    )
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    row = dict(session)

    if not row.get("interview_complete"):
        raise HTTPException(status_code=400, detail="인터뷰가 완료되지 않았습니다.")

    raw_interview = row.get("interview_data") or {}
    if isinstance(raw_interview, str):
        raw_interview = json.loads(raw_interview)

    result = await draft_graph.ainvoke({
        "session_id": session_id,
        "contract_type": row.get("contract_type", ""),
        "interview_data": dict(raw_interview),
        "interview_complete": True,
        "pending_fields": [],
        "template_clauses": [],
        "attempt": 0,
        "max_retries": 2,
        "output_format": request.output_format,
    })

    resp = result.get("response", {})
    return DraftResponse(
        session_id=session_id,
        status=resp.get("status", "completed"),
        contract_text=resp.get("contract_text"),
        review_summary=resp.get("review_summary"),
        output_path=resp.get("output_path"),
    )
