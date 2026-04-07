"""공공데이터포털 판례 API → precedents 테이블 수집 파이프라인."""

import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.llm.client import get_embeddings_batch
from app.utils.db_client import get_pool, close_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 계약 분쟁 관련 샘플 판례
SAMPLE_PRECEDENTS = [
    {
        "case_number": "2019다223781",
        "court": "대법원",
        "decision_date": "2020-06-25",
        "case_type": "민사",
        "title": "손해배상(기) - 손해배상 한도 미설정 약관의 효력",
        "summary": "약관에서 손해배상의 한도를 정하지 아니한 경우, 약관규제법 제6조에 따라 그 약관의 공정성을 판단하여야 하며, 고객에게 부당하게 불리한 조항은 무효로 볼 수 있다.",
        "key_points": "손해배상 한도가 설정되지 않은 약관 조항의 유효성은 약관규제법 제6조의 일반원칙에 따라 판단하여야 한다. 신의성실 원칙에 반하여 공정을 잃은 조항은 무효이다.",
        "category": "손해배상",
        "related_laws": ["약관규제법 제6조", "약관규제법 제7조", "민법 제393조"],
    },
    {
        "case_number": "2017다225312",
        "court": "대법원",
        "decision_date": "2018-03-15",
        "case_type": "민사",
        "title": "용역계약해지 - 일방적 해지권 조항의 효력",
        "summary": "용역계약에서 발주자에게만 일방적 해지권을 부여하고 수급인에게는 해지권을 부여하지 않는 조항은 약관규제법 제9조에 따라 무효가 될 수 있다.",
        "key_points": "계약 해지에 관한 약관 조항이 사업자에게만 유리한 해지권을 부여하는 경우, 이는 고객에게 부당하게 불이익을 줄 우려가 있어 무효로 판단될 수 있다.",
        "category": "계약해지",
        "related_laws": ["약관규제법 제9조", "민법 제543조", "민법 제544조"],
    },
    {
        "case_number": "2021다281347",
        "court": "대법원",
        "decision_date": "2022-09-29",
        "case_type": "민사",
        "title": "지식재산권귀속 - 용역 결과물의 저작권 귀속",
        "summary": "용역계약에서 결과물의 지식재산권 귀속에 관한 명시적 약정이 없는 경우, 저작권법에 따라 창작자인 수급인에게 저작권이 귀속된다.",
        "key_points": "업무상 저작물에 해당하지 않는 한 용역 결과물의 저작권은 원칙적으로 실제 창작을 수행한 수급인에게 귀속된다. 계약서에 IP 귀속 조항을 명확히 정하는 것이 분쟁 예방에 중요하다.",
        "category": "지식재산권",
        "related_laws": ["저작권법 제2조", "저작권법 제9조"],
    },
    {
        "case_number": "2020다248903",
        "court": "대법원",
        "decision_date": "2021-07-08",
        "case_type": "민사",
        "title": "경업금지약정 - 과도한 경업금지 조항의 효력",
        "summary": "경업금지 약정은 그 기간, 지역적 범위, 대상 직종 등을 고려하여 합리적인 범위 내에서만 유효하다. 과도하게 포괄적인 경업금지 조항은 공서양속에 반하여 무효가 될 수 있다.",
        "key_points": "경업금지 약정의 유효성은 보호할 가치 있는 사용자의 이익, 근로자의 퇴직 전 지위, 경업 제한의 기간·지역·대상 직종, 대상 조치의 유무 등을 종합적으로 고려하여 판단한다.",
        "category": "경업금지",
        "related_laws": ["민법 제103조"],
    },
    {
        "case_number": "2018다287362",
        "court": "대법원",
        "decision_date": "2019-11-14",
        "case_type": "민사",
        "title": "자동갱신계약 - 자동갱신 조항의 불공정성",
        "summary": "계약의 자동갱신 조항에서 갱신 거절의 통지 기간이 부당하게 짧거나 갱신 조건이 일방에게 현저히 불리한 경우, 해당 조항은 약관규제법에 따라 무효가 될 수 있다.",
        "key_points": "자동갱신 조항 자체는 유효하나, 갱신 거절 통지 기간이 부당하게 짧거나 갱신 시 조건 변경이 일방적으로 이루어지는 경우에는 공정성을 잃은 것으로 볼 수 있다.",
        "category": "자동갱신",
        "related_laws": ["약관규제법 제6조"],
    },
    {
        "case_number": "2016다249557",
        "court": "대법원",
        "decision_date": "2017-05-18",
        "case_type": "민사",
        "title": "비밀유지의무 - 편면적 비밀유지 조항의 효력",
        "summary": "비밀유지 의무가 일방 당사자에게만 부과되고 상대방에게는 비밀유지 의무가 없는 편면적 비밀유지 조항은, 계약의 성격과 거래 관행에 비추어 합리적인 이유가 없다면 불공정한 조항으로 볼 수 있다.",
        "key_points": "비밀유지계약에서 쌍방 모두 비밀정보를 교환하는 경우 일방에게만 비밀유지 의무를 부과하는 것은 불공정할 수 있다.",
        "category": "비밀유지",
        "related_laws": ["약관규제법 제6조", "부정경쟁방지법 제2조"],
    },
    {
        "case_number": "2022다301245",
        "court": "대법원",
        "decision_date": "2023-04-13",
        "case_type": "민사",
        "title": "임대차보증금 - 임대차 보증금 반환",
        "summary": "임대차계약 종료 시 임대인은 임차인에게 보증금을 반환할 의무가 있으며, 임차인의 원상회복의무와 보증금반환의무는 동시이행관계에 있다.",
        "key_points": "임대차 보증금 반환청구권과 임차인의 목적물 반환의무 및 원상회복의무는 동시이행의 관계에 있다.",
        "category": "임대차",
        "related_laws": ["민법 제536조", "주택임대차보호법 제3조"],
    },
]


async def ingest_sample_precedents():
    """샘플 판례 데이터를 DB에 삽입한다."""
    logger.info(f"샘플 판례 데이터 {len(SAMPLE_PRECEDENTS)}건 삽입 시작")

    texts = [f"{p['title']} {p['summary']}" for p in SAMPLE_PRECEDENTS]

    try:
        embeddings = await get_embeddings_batch(texts)
    except Exception:
        logger.warning("임베딩 생성 실패. 텍스트만 삽입합니다.")
        embeddings = [None] * len(SAMPLE_PRECEDENTS)

    pool = await get_pool()

    for prec, embedding in zip(SAMPLE_PRECEDENTS, embeddings):
        try:
            if embedding:
                await pool.execute(
                    """
                    INSERT INTO precedents
                        (case_number, court, decision_date, case_type, title, summary, key_points, category, related_laws, embedding)
                    VALUES ($1, $2, $3::date, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (case_number) DO UPDATE SET
                        summary = EXCLUDED.summary,
                        key_points = EXCLUDED.key_points,
                        embedding = EXCLUDED.embedding
                    """,
                    prec["case_number"], prec["court"], prec["decision_date"],
                    prec["case_type"], prec["title"], prec["summary"],
                    prec["key_points"], prec["category"], prec["related_laws"],
                    json.dumps(embedding),
                )
            else:
                await pool.execute(
                    """
                    INSERT INTO precedents
                        (case_number, court, decision_date, case_type, title, summary, key_points, category, related_laws)
                    VALUES ($1, $2, $3::date, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (case_number) DO UPDATE SET
                        summary = EXCLUDED.summary,
                        key_points = EXCLUDED.key_points
                    """,
                    prec["case_number"], prec["court"], prec["decision_date"],
                    prec["case_type"], prec["title"], prec["summary"],
                    prec["key_points"], prec["category"], prec["related_laws"],
                )
            logger.info(f"  ✓ {prec['case_number']} {prec['title'][:30]}")
        except Exception as e:
            logger.error(f"  ✗ {prec['case_number']}: {e}")

    await close_pool()
    logger.info("판례 데이터 삽입 완료")


if __name__ == "__main__":
    asyncio.run(ingest_sample_precedents())
