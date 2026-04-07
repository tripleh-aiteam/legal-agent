"""RAG 관련 Pydantic 모델."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LawResult(BaseModel):
    """법령 검색 결과."""

    law_name: str  # "민법"
    article_number: str  # "제393조"
    article_title: str | None = None
    content: str
    category: str | None = None
    score: float = 0.0


class PrecedentResult(BaseModel):
    """판례 검색 결과."""

    case_number: str  # "2023다54321"
    court: str  # "대법원"
    decision_date: str | None = None
    title: str
    summary: str
    key_points: str | None = None
    relevant_part: str | None = None  # 쿼리와 가장 관련 높은 부분
    category: str | None = None
    related_laws: list[str] = Field(default_factory=list)
    score: float = 0.0


class StandardClauseResult(BaseModel):
    """표준 계약서 조항 검색 결과."""

    contract_type: str  # "용역계약"
    clause_type: str  # "손해배상"
    standard_text: str
    is_mandatory: bool = False
    industry: str | None = None
    score: float = 0.0


class RAGResult(BaseModel):
    """RAG 통합 검색 결과."""

    laws: list[LawResult] = Field(default_factory=list)
    precedents: list[PrecedentResult] = Field(default_factory=list)
    standards: list[StandardClauseResult] = Field(default_factory=list)
    reranked_top_k: list[dict] = Field(default_factory=list)


class PrecedentSearchRequest(BaseModel):
    """판례 검색 요청."""

    query: str
    clause_id: str | None = None
    limit: int = 10
    category: str | None = None


class PrecedentSearchResponse(BaseModel):
    """판례 검색 응답."""

    results: list[PrecedentResult]
    total_count: int
