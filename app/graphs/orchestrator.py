"""Orchestrator 메인 그래프 — LangGraph StateGraph 정의.

사용자 요청을 받아 모드를 분류하고, 해당 서브그래프로 라우팅한다.

모드:
    - review: 계약서 분석 → ReviewGraph
    - draft:  계약서 생성 → DraftGraph
    - advise: 법률 상담   → AdviseGraph
"""

from langgraph.graph import END, START, StateGraph

from app.nodes.classifier import classify_intent
from app.state.orchestrator_state import OrchestratorState


def route_mode(state: OrchestratorState) -> str:
    """분류된 intent에 따라 서브그래프로 라우팅."""
    intent = state.get("intent", "review")
    if intent in ("review", "draft", "advise"):
        return intent
    return "review"  # 기본값


async def run_review(state: OrchestratorState) -> dict:
    """Review 서브그래프 실행."""
    from app.graphs.review_graph import review_graph

    # Orchestrator State → Review State 변환
    review_input = {
        "document_id": state.get("document_id", ""),
        "raw_text": state.get("raw_text", ""),
        "perspective": state.get("perspective", "neutral"),
        "focus_areas": state.get("focus_areas", []),
        "attempt": 0,
        "max_retries": 2,
        "feedback": [],
        "clause_analyses": [],
    }

    result = await review_graph.ainvoke(review_input)

    return {"response": result.get("response")}


async def run_draft(state: OrchestratorState) -> dict:
    """Draft 서브그래프 실행."""
    from app.graphs.draft_graph import draft_graph

    draft_input = {
        "session_id": state.get("session_id", ""),
        "contract_type": "",
        "interview_data": {},
        "interview_complete": False,
        "pending_fields": [],
        "template_clauses": [],
        "attempt": 0,
        "max_retries": 2,
    }

    result = await draft_graph.ainvoke(draft_input)

    return {"response": result.get("response")}


async def run_advise(state: OrchestratorState) -> dict:
    """Advise 서브그래프 실행."""
    from app.graphs.advise_graph import advise_graph

    advise_input = {
        "session_id": state.get("session_id", ""),
        "document_id": state.get("document_id", ""),
        "raw_text": state.get("raw_text", ""),
        "clauses": [],
        "message": state.get("message", ""),
        "conversation_history": [],
    }

    result = await advise_graph.ainvoke(advise_input)

    return {"response": result.get("response")}


def build_orchestrator_graph() -> StateGraph:
    """메인 Orchestrator 그래프를 빌드한다."""

    graph = StateGraph(OrchestratorState)

    # ── 노드 등록 ──
    graph.add_node("classify", classify_intent)
    graph.add_node("review", run_review)
    graph.add_node("draft", run_draft)
    graph.add_node("advise", run_advise)

    # ── 엣지 연결 ──

    # START → 모드 분류
    graph.add_edge(START, "classify")

    # 모드 분류 → 서브그래프 라우팅
    graph.add_conditional_edges(
        "classify",
        route_mode,
        {
            "review": "review",
            "draft": "draft",
            "advise": "advise",
        },
    )

    # 각 서브그래프 → END
    graph.add_edge("review", END)
    graph.add_edge("draft", END)
    graph.add_edge("advise", END)

    return graph


# 컴파일된 메인 그래프
orchestrator_graph = build_orchestrator_graph().compile()
