"""PostgreSQL (asyncpg) 데이터베이스 클라이언트."""

import asyncpg

from app.config import settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """커넥션 풀을 가져온다. 없으면 생성."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=2,
            max_size=10,
            statement_cache_size=0,
        )
    return _pool


async def close_pool() -> None:
    """커넥션 풀을 닫는다."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def execute(query: str, *args) -> str:
    """단일 SQL 실행."""
    pool = await get_pool()
    return await pool.execute(query, *args)


async def fetch(query: str, *args) -> list[asyncpg.Record]:
    """여러 행 조회."""
    pool = await get_pool()
    return await pool.fetch(query, *args)


async def fetchrow(query: str, *args) -> asyncpg.Record | None:
    """단일 행 조회."""
    pool = await get_pool()
    return await pool.fetchrow(query, *args)


async def fetchval(query: str, *args):
    """단일 값 조회."""
    pool = await get_pool()
    return await pool.fetchval(query, *args)
