"""Draft(생성) 서브그래프 — LangGraph StateGraph 정의.

파이프라인:
    Interview(multi-turn) → SearchTemplate → Generate → SelfReview → 수정/출력
"""

from langgraph.graph import END, START, StateGraph

from app.nodes.drafter import (
    export_docx,
    generate_contract,
    interview_node,
    revise_contract,
    search_template,
    self_review,
)
from app.state.draft_state import DraftState


def check_interview(state: DraftState) -> str:
    """인터뷰 완료 여부에 따라 라우팅."""
    if state.get("interview_complete", False):
        return "complete"
    return "continue"


def check_review(state: DraftState) -> str:
    """자체 검증 결과에 따라 라우팅."""
    if state.get("review_passed", False):
        return "passed"

    attempt = state.get("attempt", 0)
    max_retries = state.get("max_retries", 2)

    if attempt >= max_retries:
        return "max_retries"

    return "failed"


def build_draft_graph() -> StateGraph:
    """Draft 서브그래프를 빌드한다."""

    graph = StateGraph(DraftState)

    # ── 노드 등록 ──
    graph.add_node("interview", interview_node)
    graph.add_node("search_template", search_template)
    graph.add_node("generate", generate_contract)
    graph.add_node("self_review", self_review)
    graph.add_node("revise", revise_contract)
    graph.add_node("export", export_docx)

    # ── 엣지 연결 ──

    # START → 인터뷰
    graph.add_edge(START, "interview")

    # 인터뷰 → 완료시 서식검색 / 미완료시 END(multi-turn 응답)
    graph.add_conditional_edges(
        "interview",
        check_interview,
        {
            "complete": "search_template",
            "continue": END,  # 다음 턴에서 /draft/continue로 재진입
        },
    )

    # 서식 검색 → 생성 → 자체 검증
    graph.add_edge("search_template", "generate")
    graph.add_edge("generate", "self_review")

    # 자체 검증 → 통과/실패/최대재시도
    graph.add_conditional_edges(
        "self_review",
        check_review,
        {
            "passed": "export",
            "failed": "revise",
            "max_retries": "export",  # 최대 재시도 초과해도 출력은 함
        },
    )

    # 수정 → 재검증
    graph.add_edge("revise", "self_review")

    # 출력 → END
    graph.add_edge("export", END)

    return graph


# 컴파일된 Draft 그래프
draft_graph = build_draft_graph().compile()
