"""Advisor 노드 — 대화형 법률 상담 (Claude Sonnet + RAG).

사용자 질문 → 관련 조항 매칭 → RAG 법률 근거 검색 → 상담 응답 생성.
응답 구조: 판단 → 이유 → 법적근거 → 행동제안 → 후속질문 → 면책문구
"""

import json
import logging
import re
import uuid

from rapidfuzz import fuzz

from app.config import settings
from app.llm.client import call_llm_json
from app.llm.prompts.advisor_system import ADVISOR_SYSTEM_PROMPT
from app.state.advise_state import AdviseState
from app.utils.db_client import execute, fetch, fetchrow

logger = logging.getLogger(__name__)


def load_session(state: AdviseState) -> dict:
    """세션 로드/생성 노드."""
    session_id = state.get("session_id", "")
    document_id = state.get("document_id", "")

    if not session_id:
        session_id = str(uuid.uuid4())
        return {
            "session_id": session_id,
            "conversation_history": [],
        }

    # 기존 세션 로드는 API 레이어에서 처리
    return {
        "session_id": session_id,
        "conversation_history": state.get("conversation_history", []),
    }


def extract_clause(state: AdviseState) -> dict:
    """관련 조항 추출 노드.

    매칭 전략:
    1. 명시적: "제8조" → 조항번호 직접 매칭
    2. 키워드: "손해배상 부분" → 조항 내 키워드 검색
    3. 맥락: "그거", "위에서 말한" → 대화 히스토리에서 마지막 조항 참조
    4. 유사도: 질문과 조항 내용 fuzzy matching
    """
    message = state.get("message", "")
    clauses = state.get("clauses", [])
    history = state.get("conversation_history", [])

    if not clauses:
        return {"target_clause": None, "match_method": None}

    # 1. 명시적 매칭: "제N조"
    explicit_match = re.search(r"제\s*(\d+)\s*조", message)
    if explicit_match:
        clause_num = explicit_match.group(1)
        for clause in clauses:
            cn = clause.get("clause_number", "")
            if cn and clause_num in cn:
                return {"target_clause": clause, "match_method": "explicit"}

    # 2. 키워드 매칭
    legal_keywords = [
        "손해배상", "해지", "해제", "비밀유지", "대금", "지급", "기간", "갱신",
        "해고", "경업금지", "경쟁금지", "지식재산", "저작권", "보증금", "월세",
        "납품", "검수", "면책", "분쟁", "관할", "위약금", "계약금",
    ]
    matched_keywords = [kw for kw in legal_keywords if kw in message]
    if matched_keywords:
        best_clause = None
        best_score = 0
        for clause in clauses:
            content = clause.get("content", "") + " " + (clause.get("title") or "")
            score = sum(1 for kw in matched_keywords if kw in content)
            if score > best_score:
                best_score = score
                best_clause = clause
        if best_clause:
            return {"target_clause": best_clause, "match_method": "keyword"}

    # 3. 맥락 참조
    context_refs = ["그거", "그 조항", "위에서", "아까", "방금"]
    if any(ref in message for ref in context_refs) and history:
        # 마지막 assistant 응답에서 조항 정보 추출
        for msg in reversed(history):
            if msg.get("role") == "assistant":
                content = str(msg.get("content", ""))
                clause_ref = re.search(r"제\s*(\d+)\s*조", content)
                if clause_ref:
                    num = clause_ref.group(1)
                    for clause in clauses:
                        if num in clause.get("clause_number", ""):
                            return {"target_clause": clause, "match_method": "context"}
                break

    # 4. 유사도 기반 매칭
    best_clause = None
    best_ratio = 0
    for clause in clauses:
        content = clause.get("content", "")[:300]
        ratio = fuzz.partial_ratio(message, content)
        if ratio > best_ratio:
            best_ratio = ratio
            best_clause = clause
    if best_ratio > 50 and best_clause:
        return {"target_clause": best_clause, "match_method": "similarity"}

    return {"target_clause": None, "match_method": None}


async def generate_advice(state: AdviseState) -> dict:
    """상담 응답 생성 노드: Claude Sonnet + RAG 근거."""
    target_clause = state.get("target_clause")
    rag_results = state.get("rag_results", {})
    message = state.get("message", "")
    history = state.get("conversation_history", [])

    # 대화 히스토리 (최근 6턴)
    recent_history = history[-6:] if len(history) > 6 else history
    history_text = "\n".join(
        f"{'사용자' if m['role'] == 'user' else 'AI'}: {m['content'][:200]}"
        for m in recent_history
    )

    # 관련 조항
    clause_text = ""
    if target_clause:
        clause_text = (
            f"[관련 조항: {target_clause.get('clause_number', '')} "
            f"{target_clause.get('title', '')}]\n"
            f"{target_clause.get('content', '')}"
        )

    # RAG 근거
    rag_text_parts = []
    for law in rag_results.get("laws", [])[:3]:
        rag_text_parts.append(
            f"[법률] {law.get('law_name', '')} {law.get('article_number', '')}: "
            f"{law.get('content', '')[:200]}"
        )
    for prec in rag_results.get("precedents", [])[:3]:
        rag_text_parts.append(
            f"[판례] {prec.get('case_number', '')} ({prec.get('court', '')}): "
            f"{prec.get('summary', '')[:200]}"
        )
    rag_text = "\n".join(rag_text_parts) if rag_text_parts else "(검색된 법적 근거 없음)"

    user_prompt = ""
    if history_text:
        user_prompt += f"[대화 히스토리]\n{history_text}\n\n"
    if clause_text:
        user_prompt += f"{clause_text}\n\n"
    user_prompt += f"[법률 근거 검색 결과]\n{rag_text}\n\n"
    user_prompt += f"사용자 질문: {message}"

    try:
        result = await call_llm_json(
            model=settings.advisor_model,
            system_prompt=(
                ADVISOR_SYSTEM_PROMPT
                + '\n\nJSON 형식으로 응답하세요: {"judgment": "🔴위험/🟡주의/🟢안전", '
                '"reason": "이유", "legal_basis": {"laws": [...], "precedents": [...]}, '
                '"action_suggestion": "행동 제안", "follow_up_questions": ["질문1", "질문2"], '
                '"disclaimer": "면책문구"}'
            ),
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=2048,
        )
        advice = result["data"]

        # 면책문구 보장
        if "disclaimer" not in advice:
            advice["disclaimer"] = (
                "본 정보는 AI가 제공하는 참고 정보이며, 법률 자문이 아닙니다. "
                "중요한 법률적 결정은 반드시 변호사와 상담하세요."
            )

        return {
            "advice_response": advice,
            "response": {
                "status": "answered",
                "session_id": state.get("session_id", ""),
                "advice": advice,
                "matched_clause": {
                    "clause_number": target_clause.get("clause_number") if target_clause else None,
                    "title": target_clause.get("title") if target_clause else None,
                    "match_method": state.get("match_method"),
                } if target_clause else None,
            },
        }
    except Exception as e:
        logger.error(f"상담 응답 생성 실패: {e}")
        return {
            "advice_response": None,
            "response": {"status": "error", "error": str(e)},
        }


def update_session(state: AdviseState) -> dict:
    """세션 업데이트 노드: 대화 히스토리에 현재 턴 추가."""
    history = list(state.get("conversation_history", []))
    message = state.get("message", "")
    advice = state.get("advice_response")

    history.append({"role": "user", "content": message})
    if advice:
        # 간결한 요약을 히스토리에 저장
        summary = f"{advice.get('judgment', '')}: {advice.get('reason', '')[:200]}"
        history.append({"role": "assistant", "content": summary})

    # 히스토리 길이 제한 (최근 20턴)
    if len(history) > 20:
        history = history[-20:]

    return {"conversation_history": history}
