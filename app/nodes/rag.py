"""RAG 노드 — 법률 근거 검색 (Hybrid Search).

법령/판례/표준계약서에서 관련 근거를 검색한다.
1. 쿼리 생성 (LLM)
2. 3개 소스 병렬 검색 (법령/판례/표준조항)
3. RRF 통합 + Reranking
"""

import asyncio
import json
import logging

from app.config import settings
from app.llm.client import call_llm_json, get_embedding
from app.llm.prompts.rag_query_gen import RAG_QUERY_GEN_PROMPT
from app.state.advise_state import AdviseState
from app.state.review_state import ReviewState
from app.utils.db_client import fetch

logger = logging.getLogger(__name__)


async def rag_search(state: ReviewState) -> dict:
    """Review 모드용 RAG 검색 노드."""
    clauses = state.get("clauses", [])
    if not clauses:
        return {"rag_results": {"laws": [], "precedents": [], "standards": []}}

    # 주요 조항에서 검색 쿼리 생성 (최대 5개 조항)
    target_clauses = clauses[:5]
    combined_text = "\n\n".join(c.get("content", "")[:500] for c in target_clauses)

    queries = await _generate_queries(combined_text)

    # 3개 소스 병렬 검색
    law_results, precedent_results, standard_results = await asyncio.gather(
        _search_laws(queries),
        _search_precedents(queries),
        _search_standard_clauses(queries, state.get("doc_type")),
    )

    # Reranking (간단 버전: 점수 기반 정렬)
    all_results = (
        [{"type": "law", **r} for r in law_results]
        + [{"type": "precedent", **r} for r in precedent_results]
        + [{"type": "standard", **r} for r in standard_results]
    )
    all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    top_k = all_results[:20]

    return {
        "rag_results": {
            "laws": law_results,
            "precedents": precedent_results,
            "standards": standard_results,
            "reranked_top_k": top_k,
        }
    }


async def advise_rag_search(state: AdviseState) -> dict:
    """Advise 모드용 RAG 검색 노드. 속도 우선 (limit=5)."""
    target_clause = state.get("target_clause")
    message = state.get("message", "")

    search_text = ""
    if target_clause:
        search_text = target_clause.get("content", "")[:300]
    if message:
        search_text = f"{message}\n{search_text}"

    if not search_text.strip():
        return {"rag_results": {"laws": [], "precedents": [], "standards": []}}

    queries = await _generate_queries(search_text)

    law_results, precedent_results, standard_results = await asyncio.gather(
        _search_laws(queries, limit=3),
        _search_precedents(queries, limit=3),
        _search_standard_clauses(queries, limit=2),
    )

    return {
        "rag_results": {
            "laws": law_results,
            "precedents": precedent_results,
            "standards": standard_results,
        }
    }


# ──────────────────────────────────────────
# 내부 함수
# ──────────────────────────────────────────

async def _generate_queries(clause_text: str) -> list[dict]:
    """조항 텍스트에서 검색 쿼리 3~5개를 생성한다."""
    try:
        result = await call_llm_json(
            model=settings.classifier_model,  # GPT-4o-mini (저렴)
            system_prompt=RAG_QUERY_GEN_PROMPT,
            user_prompt=f"다음 계약서 조항을 분석하여 검색 쿼리를 생성하세요:\n\n{clause_text}",
            max_tokens=1024,
        )
        queries = result["data"].get("queries", [])
        return queries[:5]
    except Exception as e:
        logger.warning(f"쿼리 생성 실패, 폴백 사용: {e}")
        # 폴백: 원문 텍스트를 직접 쿼리로 사용
        return [
            {"text": clause_text[:200], "type": "semantic", "target": "laws"},
            {"text": clause_text[:200], "type": "semantic", "target": "precedents"},
        ]


async def _search_laws(queries: list[dict], limit: int = 5) -> list[dict]:
    """법령 DB에서 Hybrid Search."""
    results = []

    semantic_queries = [q for q in queries if q.get("target") in ("laws", None)]
    if not semantic_queries:
        semantic_queries = queries[:2]

    for query in semantic_queries[:3]:
        try:
            query_text = query["text"]
            query_embedding = await get_embedding(query_text)
            embedding_str = json.dumps(query_embedding)

            rows = await fetch(
                "SELECT * FROM hybrid_search_laws($1::vector, $2, $3)",
                embedding_str, query_text, limit,
            )

            for row in rows:
                results.append({
                    "law_name": row["law_name"],
                    "article_number": row["article_number"],
                    "article_title": row.get("article_title", ""),
                    "content": row["content"],
                    "score": float(row["combined_score"]),
                })
        except Exception as e:
            logger.warning(f"법령 검색 실패 (쿼리: {query.get('text', '')[:30]}): {e}")

    # 중복 제거 (법률명+조번호 기준)
    seen = set()
    unique = []
    for r in results:
        key = f"{r['law_name']}_{r['article_number']}"
        if key not in seen:
            seen.add(key)
            unique.append(r)

    unique.sort(key=lambda x: x["score"], reverse=True)
    return unique[:limit]


async def _search_precedents(queries: list[dict], limit: int = 5) -> list[dict]:
    """판례 DB에서 Hybrid Search."""
    results = []

    semantic_queries = [q for q in queries if q.get("target") in ("precedents", None)]
    if not semantic_queries:
        semantic_queries = queries[:2]

    for query in semantic_queries[:3]:
        try:
            query_text = query["text"]
            query_embedding = await get_embedding(query_text)
            embedding_str = json.dumps(query_embedding)

            rows = await fetch(
                "SELECT * FROM hybrid_search_precedents($1::vector, $2, $3)",
                embedding_str, query_text, limit,
            )

            for row in rows:
                results.append({
                    "case_number": row["case_number"],
                    "court": row["court"],
                    "title": row["title"],
                    "summary": row["summary"],
                    "key_points": row.get("key_points", ""),
                    "score": float(row["combined_score"]),
                })
        except Exception as e:
            logger.warning(f"판례 검색 실패: {e}")

    seen = set()
    unique = []
    for r in results:
        if r["case_number"] not in seen:
            seen.add(r["case_number"])
            unique.append(r)

    unique.sort(key=lambda x: x["score"], reverse=True)
    return unique[:limit]


async def _search_standard_clauses(
    queries: list[dict], contract_type: str | None = None, limit: int = 3
) -> list[dict]:
    """표준 계약서 조항 벡터 검색."""
    results = []

    semantic_queries = [q for q in queries if q.get("target") in ("standards", None)]
    if not semantic_queries:
        semantic_queries = queries[:1]

    for query in semantic_queries[:2]:
        try:
            query_text = query["text"]
            query_embedding = await get_embedding(query_text)
            embedding_str = json.dumps(query_embedding)

            if contract_type:
                rows = await fetch(
                    """
                    SELECT *, 1 - (embedding <=> $1::vector) AS score
                    FROM standard_clauses
                    WHERE contract_type = $2
                    ORDER BY embedding <=> $1::vector
                    LIMIT $3
                    """,
                    embedding_str, contract_type, limit,
                )
            else:
                rows = await fetch(
                    """
                    SELECT *, 1 - (embedding <=> $1::vector) AS score
                    FROM standard_clauses
                    ORDER BY embedding <=> $1::vector
                    LIMIT $2
                    """,
                    embedding_str, limit,
                )

            for row in rows:
                results.append({
                    "contract_type": row["contract_type"],
                    "clause_type": row["clause_type"],
                    "standard_text": row["standard_text"],
                    "is_mandatory": row["is_mandatory"],
                    "score": float(row.get("score", 0)),
                })
        except Exception as e:
            logger.warning(f"표준 조항 검색 실패: {e}")

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]
