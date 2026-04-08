"""FastAPI 메인 애플리케이션."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config import settings
from app.utils.db_client import close_pool

logging.basicConfig(level=getattr(logging, settings.log_level))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 수명 주기: 시작/종료 시 리소스 관리."""
    logger.info("Legal Review Agent 시작")
    yield
    await close_pool()
    logger.info("Legal Review Agent 종료")


app = FastAPI(
    title="Legal Review Agent",
    description="법률 계약서 검토/생성/상담 멀티 에이전트 시스템",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터 등록
app.include_router(api_router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "legal-review-agent", "version": "0.1.0"}
