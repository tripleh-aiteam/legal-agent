"""API v1 라우터 통합."""

from fastapi import APIRouter

from app.api.v1 import advise, analysis, documents, draft, laws, precedents, reports

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(analysis.router, prefix="/analysis", tags=["analysis"])
api_router.include_router(laws.router, prefix="/laws", tags=["laws"])
api_router.include_router(precedents.router, prefix="/precedents", tags=["precedents"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(draft.router, prefix="/draft", tags=["draft"])
api_router.include_router(advise.router, prefix="/advise", tags=["advise"])
