"""Review(분석) 서브그래프 — LangGraph StateGraph 정의.

파이프라인:
    SecurityScan → Parse → RAG → Analyzer(RAG 근거 포함) → Merge → Validate → 재시도(max 2)
"""

from langgraph.graph import END, START, StateGraph

from app.nodes.analyzer import analyze_clauses, retry_with_feedback
from app.nodes.merger import merge_results
from app.nodes.parser import parse_document
from app.nodes.rag import rag_search
from app.nodes.security import security_scan
from app.nodes.validator import validate
from app.state.review_state import ReviewState


def check_security(state: ReviewState) -> str:
    """보안 스캔 결과에 따라 라우팅."""
    if state.get("security_status") == "blocked":
        return "blocked"
    return "clean"


def check_validation(state: ReviewState) -> str:
    """검증 결과에 따라 라우팅."""
    if state.get("validation_passed", False):
        return "passed"

    attempt = state.get("attempt", 0)
    max_retries = state.get("max_retries", 2)

    if attempt >= max_retries:
        return "max_retries"

    return "failed"


def build_review_graph() -> StateGraph:
    """Review 서브그래프를 빌드한다."""

    graph = StateGraph(ReviewState)

    # ── 노드 등록 ──
    graph.add_node("security_scan", security_scan)
    graph.add_node("parse_document", parse_document)
    graph.add_node("rag_search", rag_search)
    graph.add_node("analyze_clauses", analyze_clauses)
    graph.add_node("merge_results", merge_results)
    graph.add_node("validate", validate)
    graph.add_node("retry_analyze", retry_with_feedback)

    # ── 엣지 연결 ──

    # START → 보안 스캔
    graph.add_edge(START, "security_scan")

    # 보안 스캔 → 통과/차단
    graph.add_conditional_edges(
        "security_scan",
        check_security,
        {
            "clean": "parse_document",
            "blocked": END,
        },
    )

    # 파싱 → RAG 검색 → Analyzer (RAG 결과를 근거로 분석)
    graph.add_edge("parse_document", "rag_search")
    graph.add_edge("rag_search", "analyze_clauses")

    # Analyzer → 결과 병합
    graph.add_edge("analyze_clauses", "merge_results")

    # 병합 → 검증
    graph.add_edge("merge_results", "validate")

    # 검증 → 통과/실패/최대재시도
    graph.add_conditional_edges(
        "validate",
        check_validation,
        {
            "passed": END,
            "failed": "retry_analyze",
            "max_retries": END,
        },
    )

    # 재분석 → 검증 (루프)
    graph.add_edge("retry_analyze", "validate")

    return graph


# 컴파일된 Review 그래프
review_graph = build_review_graph().compile()
