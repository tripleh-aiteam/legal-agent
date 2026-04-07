"""classify_intent 노드 — 사용자 요청을 3모드로 분류.

GPT-4o-mini를 사용하여 요청 유형을 판별한다.
- review: 문서가 있고 "검토해줘" → 분석 모드
- draft:  문서가 없고 "만들어줘" → 생성 모드
- advise: 문서가 있고 "이거 괜찮아?" → 상담 모드
"""

from app.config import settings
from app.llm.client import call_llm_json
from app.state.orchestrator_state import OrchestratorState

CLASSIFIER_SYSTEM_PROMPT = """당신은 법률 AI 서비스의 요청 분류기입니다.
사용자 요청을 다음 3가지 모드 중 하나로 분류하세요:

1. "review" - 계약서/문서를 분석/검토해달라는 요청 (문서가 첨부됨)
2. "draft" - 계약서를 새로 만들어달라는 요청 (문서가 없음)
3. "advise" - 특정 조항에 대한 상담/질문 (대화형)

반드시 JSON으로 응답하세요: {"intent": "review|draft|advise", "confidence": 0.0~1.0}
"""


def classify_intent(state: OrchestratorState) -> dict:
    """요청을 3모드로 분류하는 노드."""

    # 명시적 request_type이 있으면 그대로 사용
    if state.get("request_type") in ("review", "draft", "advise"):
        return {"intent": state["request_type"]}

    # 힌트 기반 분류: 문서 유무 + 메시지 내용
    has_document = bool(state.get("document_id") or state.get("raw_text"))
    message = state.get("message", "")

    # 간단한 규칙 기반 분류 (LLM 호출 전 빠른 판단)
    if not has_document and message:
        # 문서 없이 메시지만 → draft 가능성 높음
        draft_keywords = ["만들어", "작성", "생성", "계약서 써", "계약서를 만"]
        if any(kw in message for kw in draft_keywords):
            return {"intent": "draft"}

    if has_document and message:
        # 문서 + 특정 질문 → advise 가능성
        advise_keywords = ["괜찮", "싸인해도", "문제없", "어때", "질문", "찝찝"]
        if any(kw in message for kw in advise_keywords):
            return {"intent": "advise"}

    # 문서가 있으면 기본 review
    if has_document:
        return {"intent": "review"}

    # 그 외: LLM으로 분류
    # TODO: Phase 5에서 LLM 기반 분류 구현
    return {"intent": "review"}
