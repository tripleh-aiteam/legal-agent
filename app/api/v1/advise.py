"""상담(Advise) API — Advise 그래프 호출."""

import json
import logging

from fastapi import APIRouter, HTTPException

from app.graphs.advise_graph import advise_graph
from app.models.advise import AdviseRequest, AdviseResponse
from app.parsers.clause_splitter import split_clauses
from app.utils.db_client import execute, fetch, fetchrow

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/message", response_model=AdviseResponse)
async def advise_message(request: AdviseRequest):
    """법률 상담 메시지 (대화형)."""

    # 문서 조회
    doc = await fetchrow(
        "SELECT id, raw_text, language FROM documents WHERE id = $1",
        str(request.document_id),
    )
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    if not doc["raw_text"]:
        raise HTTPException(status_code=400, detail="문서 텍스트가 파싱되지 않았습니다.")

    # 조항 분리
    clauses = split_clauses(doc["raw_text"], language=doc.get("language", "ko"))

    # 세션 로드
    session_id = request.session_id
    conversation_history = []

    if session_id:
        session = await fetchrow(
            "SELECT * FROM advise_sessions WHERE id = $1::uuid",
            session_id,
        )
        if session:
            conversation_history = session.get("conversation_history", [])
            if isinstance(conversation_history, str):
                conversation_history = json.loads(conversation_history)
    else:
        # 새 세션 생성
        row = await fetchrow(
            """
            INSERT INTO advise_sessions (document_id, conversation_history)
            VALUES ($1, '[]'::jsonb)
            RETURNING id
            """,
            str(request.document_id),
        )
        session_id = str(row["id"])

    # Advise 그래프 실행
    try:
        result = await advise_graph.ainvoke({
            "session_id": session_id,
            "document_id": str(request.document_id),
            "raw_text": doc["raw_text"],
            "clauses": clauses,
            "message": request.message,
            "conversation_history": conversation_history,
        })
    except Exception as e:
        logger.error(f"Advise 그래프 실행 실패: {e}")
        return AdviseResponse(
            session_id=session_id,
            status="error",
            error=str(e),
        )

    # 세션 업데이트 (대화 히스토리 저장)
    updated_history = result.get("conversation_history", conversation_history)
    try:
        await execute(
            """
            UPDATE advise_sessions
            SET conversation_history = $1::jsonb, last_active_at = NOW()
            WHERE id = $2::uuid
            """,
            json.dumps(updated_history, ensure_ascii=False),
            session_id,
        )
    except Exception as e:
        logger.warning(f"세션 업데이트 실패: {e}")

    resp = result.get("response", {})
    return AdviseResponse(
        session_id=session_id,
        status=resp.get("status", "answered"),
        advice=resp.get("advice"),
        matched_clause=resp.get("matched_clause"),
        error=resp.get("error"),
    )
