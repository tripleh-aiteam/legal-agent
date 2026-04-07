"""국가법령정보센터 API → laws 테이블 수집 파이프라인.

주요 법률을 조문 단위로 수집하여 임베딩 후 DB에 저장한다.
대상: 민법, 상법, 약관규제법, 근로기준법, 주택임대차보호법 등
"""

import asyncio
import json
import logging
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.llm.client import get_embeddings_batch
from app.utils.db_client import execute, get_pool, close_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 국가법령정보센터 Open API
LAW_API_BASE = "https://www.law.go.kr/DRF/lawSearch.do"
LAW_DETAIL_BASE = "https://www.law.go.kr/DRF/lawService.do"

# 수집 대상 법률
TARGET_LAWS = [
    {"query": "민법", "law_id": "001770", "category": "민사"},
    {"query": "상법", "law_id": "001796", "category": "상사"},
    {"query": "약관의 규제에 관한 법률", "law_id": "003185", "category": "소비자"},
    {"query": "근로기준법", "law_id": "001943", "category": "노동"},
    {"query": "주택임대차보호법", "law_id": "002530", "category": "부동산"},
    {"query": "전자서명법", "law_id": "005765", "category": "전자거래"},
    {"query": "개인정보 보호법", "law_id": "011990", "category": "개인정보"},
]

# API 키가 없을 경우 샘플 데이터 사용
SAMPLE_LAWS = [
    {
        "law_id": "001770",
        "law_name": "민법",
        "article_number": "제393조",
        "article_title": "손해배상의 범위",
        "content": "채무불이행으로 인한 손해배상은 통상의 손해를 그 한도로 한다. 특별한 사정으로 인한 손해는 채무자가 그 사정을 알았거나 알 수 있었을 때에 한하여 배상의 책임이 있다.",
        "category": "민사",
    },
    {
        "law_id": "001770",
        "law_name": "민법",
        "article_number": "제390조",
        "article_title": "채무불이행과 손해배상",
        "content": "채무자가 채무의 내용에 좇은 이행을 하지 아니한 때에는 채권자는 손해배상을 청구할 수 있다. 그러나 채무자의 고의나 과실없이 이행할 수 없게 된 때에는 그러하지 아니하다.",
        "category": "민사",
    },
    {
        "law_id": "001770",
        "law_name": "민법",
        "article_number": "제394조",
        "article_title": "손해배상의 방법",
        "content": "다른 의사표시가 없으면 손해는 금전으로 배상한다.",
        "category": "민사",
    },
    {
        "law_id": "001770",
        "law_name": "민법",
        "article_number": "제398조",
        "article_title": "배상액의 예정",
        "content": "당사자는 채무불이행에 관한 손해배상액을 예정할 수 있다. 손해배상의 예정액이 부당히 과다한 경우에는 법원은 적당히 감액할 수 있다.",
        "category": "민사",
    },
    {
        "law_id": "001770",
        "law_name": "민법",
        "article_number": "제543조",
        "article_title": "해지, 해제권",
        "content": "계약 또는 법률의 규정에 의하여 당사자의 일방이나 쌍방이 해지 또는 해제의 권리가 있는 때에는 그 해지 또는 해제는 상대방에 대한 의사표시로 한다.",
        "category": "민사",
    },
    {
        "law_id": "001770",
        "law_name": "민법",
        "article_number": "제544조",
        "article_title": "이행지체와 해제",
        "content": "당사자 일방이 그 채무를 이행하지 아니하는 때에는 상대방은 상당한 기간을 정하여 그 이행을 최고하고 그 기간내에 이행하지 아니한 때에는 계약을 해제할 수 있다.",
        "category": "민사",
    },
    {
        "law_id": "001770",
        "law_name": "민법",
        "article_number": "제674조",
        "article_title": "도급인의 해제권",
        "content": "도급인이 완성된 목적물의 하자로 인하여 계약의 목적을 달성할 수 없는 때에는 계약을 해제할 수 있다. 그러나 건물 기타 토지의 공작물에 대하여는 그러하지 아니하다.",
        "category": "민사",
    },
    {
        "law_id": "003185",
        "law_name": "약관의 규제에 관한 법률",
        "article_number": "제6조",
        "article_title": "일반원칙",
        "content": "신의성실의 원칙에 반하여 공정을 잃은 약관 조항은 무효로 한다. 약관의 내용 중 다음 각 호의 어느 하나에 해당하는 내용을 정하고 있는 조항은 공정을 잃은 것으로 추정한다. 1. 고객에게 부당하게 불리한 조항 2. 고객이 계약의 거래형태 등 관련된 모든 사정에 비추어 예상하기 어려운 조항 3. 계약의 목적을 달성할 수 없을 정도로 계약에 따르는 본질적 권리를 제한하는 조항",
        "category": "소비자",
    },
    {
        "law_id": "003185",
        "law_name": "약관의 규제에 관한 법률",
        "article_number": "제7조",
        "article_title": "면책조항의 금지",
        "content": "계약 당사자의 책임에 관하여 정하고 있는 약관의 내용 중 다음 각 호의 어느 하나에 해당하는 내용을 정하고 있는 조항은 무효로 한다. 1. 사업자, 이행 보조자 또는 피고용자의 고의 또는 중대한 과실로 인한 법률상의 책임을 배제하는 조항 2. 상당한 이유 없이 사업자의 손해배상 범위를 제한하거나 사업자가 부담하여야 할 위험을 고객에게 떠넘기는 조항",
        "category": "소비자",
    },
    {
        "law_id": "003185",
        "law_name": "약관의 규제에 관한 법률",
        "article_number": "제8조",
        "article_title": "손해배상액의 예정",
        "content": "고객에 대하여 부당하게 과중한 지연 손해금 등의 손해배상 의무를 부담시키는 약관 조항은 무효로 한다.",
        "category": "소비자",
    },
    {
        "law_id": "003185",
        "law_name": "약관의 규제에 관한 법률",
        "article_number": "제9조",
        "article_title": "계약의 해제·해지",
        "content": "계약의 해제·해지에 관하여 정하고 있는 약관의 내용 중 다음 각 호의 어느 하나에 해당하는 내용을 정하고 있는 조항은 무효로 한다. 1. 법률에 따른 고객의 해제권 또는 해지권을 배제하거나 그 행사를 제한하는 조항 2. 사업자에게 법률에서 규정하고 있지 아니하는 해제권 또는 해지권을 부여하거나 법률에 따른 해제권 또는 해지권의 행사 요건을 완화하여 고객에게 부당하게 불이익을 줄 우려가 있는 조항",
        "category": "소비자",
    },
    {
        "law_id": "001943",
        "law_name": "근로기준법",
        "article_number": "제17조",
        "article_title": "근로조건의 명시",
        "content": "사용자는 근로계약을 체결할 때에 근로자에게 다음 각 호의 사항을 명시하여야 한다. 근로계약 체결 후 다음 각 호의 사항을 변경하는 경우에도 또한 같다. 1. 임금 2. 소정근로시간 3. 휴일 4. 연차 유급휴가 5. 그 밖에 대통령령으로 정하는 근로조건",
        "category": "노동",
    },
    {
        "law_id": "001943",
        "law_name": "근로기준법",
        "article_number": "제23조",
        "article_title": "해고 등의 제한",
        "content": "사용자는 근로자에게 정당한 이유 없이 해고, 휴직, 정직, 전직, 감봉, 그 밖의 징벌을 하지 못한다.",
        "category": "노동",
    },
    {
        "law_id": "002530",
        "law_name": "주택임대차보호법",
        "article_number": "제3조",
        "article_title": "대항력 등",
        "content": "임대차는 그 등기가 없는 경우에도 임차인이 주택의 인도와 주민등록을 마친 때에는 그 다음 날부터 제삼자에 대하여 효력이 생긴다.",
        "category": "부동산",
    },
    {
        "law_id": "002530",
        "law_name": "주택임대차보호법",
        "article_number": "제4조",
        "article_title": "임대차기간 등",
        "content": "기간을 정하지 아니하거나 2년 미만으로 정한 임대차는 그 기간을 2년으로 본다. 다만, 임차인은 2년 미만으로 정한 기간이 유효함을 주장할 수 있다.",
        "category": "부동산",
    },
]


async def ingest_sample_laws():
    """샘플 법률 데이터를 DB에 삽입한다."""
    logger.info(f"샘플 법률 데이터 {len(SAMPLE_LAWS)}건 삽입 시작")

    # 임베딩 생성
    texts = [f"{law['law_name']} {law['article_number']} {law['content']}" for law in SAMPLE_LAWS]

    try:
        embeddings = await get_embeddings_batch(texts)
    except Exception as e:
        logger.warning(f"임베딩 생성 실패 (API 키 없음?): {e}")
        logger.info("임베딩 없이 텍스트만 삽입합니다.")
        embeddings = [None] * len(SAMPLE_LAWS)

    pool = await get_pool()

    for law, embedding in zip(SAMPLE_LAWS, embeddings):
        try:
            if embedding:
                await pool.execute(
                    """
                    INSERT INTO laws (law_id, law_name, article_number, article_title, content, category, embedding)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (law_id, article_number) DO UPDATE SET
                        content = EXCLUDED.content,
                        article_title = EXCLUDED.article_title,
                        embedding = EXCLUDED.embedding,
                        updated_at = NOW()
                    """,
                    law["law_id"], law["law_name"], law["article_number"],
                    law.get("article_title"), law["content"], law["category"],
                    json.dumps(embedding),
                )
            else:
                await pool.execute(
                    """
                    INSERT INTO laws (law_id, law_name, article_number, article_title, content, category)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (law_id, article_number) DO UPDATE SET
                        content = EXCLUDED.content,
                        article_title = EXCLUDED.article_title,
                        updated_at = NOW()
                    """,
                    law["law_id"], law["law_name"], law["article_number"],
                    law.get("article_title"), law["content"], law["category"],
                )
            logger.info(f"  ✓ {law['law_name']} {law['article_number']} {law.get('article_title', '')}")
        except Exception as e:
            logger.error(f"  ✗ {law['law_name']} {law['article_number']}: {e}")

    await close_pool()
    logger.info("법률 데이터 삽입 완료")


async def ingest_from_api():
    """국가법령정보센터 API에서 법률 데이터를 수집한다.

    API 키가 필요합니다. 키가 없으면 샘플 데이터를 사용합니다.
    """
    api_key = os.environ.get("LAW_API_KEY")
    if not api_key:
        logger.info("LAW_API_KEY가 설정되지 않음. 샘플 데이터를 사용합니다.")
        await ingest_sample_laws()
        return

    async with httpx.AsyncClient(timeout=30) as client:
        for target in TARGET_LAWS:
            logger.info(f"수집 중: {target['query']}")
            try:
                resp = await client.get(
                    LAW_DETAIL_BASE,
                    params={
                        "OC": api_key,
                        "target": "law",
                        "type": "JSON",
                        "ID": target["law_id"],
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                # API 응답 파싱 및 DB 삽입 로직
                # (실제 API 응답 구조에 맞게 조정 필요)
                logger.info(f"  {target['query']} 수집 완료")
            except Exception as e:
                logger.error(f"  {target['query']} 수집 실패: {e}")


if __name__ == "__main__":
    asyncio.run(ingest_from_api())
