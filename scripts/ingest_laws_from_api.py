"""법제처 국가법령정보센터 API에서 법률 조문을 수집하여 DB에 저장.

사용법:
    python scripts/ingest_laws_from_api.py

수집 대상: 계약서 분석에 필요한 핵심 법률
"""

import asyncio
import logging
import sys
import xml.etree.ElementTree as ET

import asyncpg
import httpx

sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

import os

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# 법제처 API 설정
LAW_API_BASE = "https://www.law.go.kr/DRF"
OC = "chetera"  # 공개 테스트 키

# 수집할 법률 목록 (법령명 → 검색어)
TARGET_LAWS = [
    "민법",
    "상법",
    "약관의 규제에 관한 법률",
    "근로기준법",
    "개인정보 보호법",
    "부정경쟁방지 및 영업비밀보호에 관한 법률",
    "저작권법",
    "민사소송법",
    "전자서명법",
    "주택임대차보호법",
    "상가건물 임대차보호법",
    "하도급거래 공정화에 관한 법률",
    "독점규제 및 공정거래에 관한 법률",
    "전자상거래 등에서의 소비자보호에 관한 법률",
    "정보통신망 이용촉진 및 정보보호 등에 관한 법률",
    "특허법",
    "소프트웨어 진흥법",
]


async def search_law_mst(client: httpx.AsyncClient, query: str) -> tuple[str, str] | None:
    """법령 검색 → (법령명, MST 번호) 반환."""
    resp = await client.get(
        f"{LAW_API_BASE}/lawSearch.do",
        params={
            "OC": OC,
            "target": "law",
            "type": "XML",
            "query": query,
            "display": "10",
        },
        timeout=15,
    )
    root = ET.fromstring(resp.text)

    for item in root.findall(".//law"):
        name = item.findtext("법령명한글", "")
        mst = item.findtext("법령일련번호", "")
        # 정확히 일치하는 법률 찾기 (시행령/시행규칙 제외)
        if name == query and mst:
            return name, mst

    # 정확히 일치 안 하면 첫 번째 결과 (시행령/시행규칙 제외)
    for item in root.findall(".//law"):
        name = item.findtext("법령명한글", "")
        mst = item.findtext("법령일련번호", "")
        if mst and "시행령" not in name and "시행규칙" not in name:
            return name, mst

    return None


async def fetch_law_articles(
    client: httpx.AsyncClient, law_name: str, mst: str
) -> list[dict]:
    """법령 MST 번호로 조문 전체 조회."""
    resp = await client.get(
        f"{LAW_API_BASE}/lawService.do",
        params={
            "OC": OC,
            "target": "law",
            "MST": mst,
            "type": "XML",
        },
        timeout=60,
    )
    root = ET.fromstring(resp.text)

    articles = []
    for article_el in root.findall(".//조문단위"):
        num_text = (article_el.findtext("조문번호") or "").strip()
        title = (article_el.findtext("조문제목") or "").strip()
        content = (article_el.findtext("조문내용") or "").strip()

        if not num_text or not content:
            continue

        try:
            num = int(num_text)
        except ValueError:
            continue

        if num <= 0:
            continue

        # 항 내용 수집
        hang_parts = []
        for hang in article_el.findall(".//항"):
            hang_content = (hang.findtext("항내용") or "").strip()
            if hang_content:
                hang_parts.append(hang_content)

        # 항이 있으면 항 내용을 합침, 없으면 조문내용 사용
        full_content = content
        if hang_parts:
            full_content = content + "\n" + "\n".join(hang_parts)

        articles.append({
            "law_name": law_name,
            "article_number": f"제{num}조",
            "article_title": title,
            "content": full_content.strip(),
        })

    return articles


async def save_to_db(conn: asyncpg.Connection, articles: list[dict]) -> int:
    """조문을 DB에 저장."""
    count = 0
    for art in articles:
        law_id = f"{art['law_name']}_{art['article_number']}"
        try:
            await conn.execute(
                """
                INSERT INTO laws (law_id, law_name, article_number, article_title, content)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (law_id) DO UPDATE SET
                    article_title = EXCLUDED.article_title,
                    content = EXCLUDED.content
                """,
                law_id,
                art["law_name"],
                art["article_number"],
                art["article_title"],
                art["content"],
            )
            count += 1
        except Exception as e:
            logger.warning(f"  저장 실패 ({art['article_number']}): {e}")
    return count


async def main():
    logger.info("=== 법제처 API 법률 조문 수집 시작 ===\n")

    conn = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)

    async with httpx.AsyncClient() as client:
        total = 0

        for query in TARGET_LAWS:
            logger.info(f"[검색] {query}...")
            result = await search_law_mst(client, query)

            if not result:
                logger.warning(f"  ❌ '{query}' 검색 결과 없음")
                continue

            law_name, mst = result
            logger.info(f"  → {law_name} (MST={mst})")

            articles = await fetch_law_articles(client, law_name, mst)
            logger.info(f"  → {len(articles)}개 조문 추출")

            saved = await save_to_db(conn, articles)
            total += saved
            logger.info(f"  → {saved}개 저장 완료")
            logger.info("")

    # 최종 통계
    row = await conn.fetchrow("SELECT COUNT(*) as cnt FROM laws")
    logger.info(f"=== 완료: {total}건 저장, DB 총 {row['cnt']}건 ===")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
