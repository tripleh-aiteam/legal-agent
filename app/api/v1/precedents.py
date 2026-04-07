"""판례 검색 API."""

from fastapi import APIRouter, HTTPException

from app.models.rag import PrecedentSearchRequest, PrecedentSearchResponse

router = APIRouter()


@router.post("/search", response_model=PrecedentSearchResponse)
async def search_precedents(request: PrecedentSearchRequest):
    """판례 검색."""
    # TODO: Phase 4에서 구현
    raise HTTPException(status_code=501, detail="Phase 4에서 구현 예정")
