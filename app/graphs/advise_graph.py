"""Advise(상담) 서브그래프 — LangGraph StateGraph 정의.

파이프라인:
    LoadSession → ExtractClause → RAGSearch → GenerateAdvice → UpdateSession
"""

from langgraph.graph import END, START, StateGraph

from app.nodes.advisor import (
    extract_clause,
    generate_advice,
    load_session,
    update_session,
)
from app.nodes.rag import advise_rag_search
from app.state.advise_state import AdviseState


def build_advise_graph() -> StateGraph:
    """Advise 서브그래프를 빌드한다."""

    graph = StateGraph(AdviseState)

    # ── 노드 등록 ──
    graph.add_node("load_session", load_session)
    graph.add_node("extract_clause", extract_clause)
    graph.add_node("rag_search", advise_rag_search)
    graph.add_node("generate_advice", generate_advice)
    graph.add_node("update_session", update_session)

    # ── 엣지 연결 (순차) ──
    graph.add_edge(START, "load_session")
    graph.add_edge("load_session", "extract_clause")
    graph.add_edge("extract_clause", "rag_search")
    graph.add_edge("rag_search", "generate_advice")
    graph.add_edge("generate_advice", "update_session")
    graph.add_edge("update_session", END)

    return graph


# 컴파일된 Advise 그래프
advise_graph = build_advise_graph().compile()
