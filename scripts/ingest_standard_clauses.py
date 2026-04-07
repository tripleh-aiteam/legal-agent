"""표준 계약서 조항 → standard_clauses 테이블 수집 파이프라인."""

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

SAMPLE_STANDARD_CLAUSES = [
    # 용역계약 표준 조항
    {
        "contract_type": "service_contract",
        "clause_type": "손해배상",
        "standard_text": "갑 또는 을이 본 계약을 위반하여 상대방에게 손해를 끼친 경우, 그 손해를 배상하여야 한다. 다만, 손해배상의 총액은 본 계약에서 정한 계약금액을 한도로 하며, 직접적이고 통상적인 손해에 한한다.",
        "is_mandatory": True,
        "industry": None,
    },
    {
        "contract_type": "service_contract",
        "clause_type": "해지",
        "standard_text": "갑 또는 을은 상대방이 본 계약의 중대한 조항을 위반한 경우, 30일의 시정 기간을 부여한 후에도 시정되지 아니한 때에는 서면 통지로 본 계약을 해지할 수 있다. 갑 또는 을은 30일 전 서면 통지로 특별한 사유 없이도 본 계약을 해지할 수 있다.",
        "is_mandatory": True,
        "industry": None,
    },
    {
        "contract_type": "service_contract",
        "clause_type": "지식재산권",
        "standard_text": "을이 본 계약의 이행 과정에서 창작한 결과물에 대한 지식재산권은 갑에게 귀속된다. 다만, 을이 본 계약 체결 이전에 보유하고 있던 지식재산권은 을에게 유보되며, 갑은 본 계약의 목적 범위 내에서 이를 사용할 수 있는 비독점적 라이선스를 부여받는다.",
        "is_mandatory": False,
        "industry": "IT",
    },
    {
        "contract_type": "service_contract",
        "clause_type": "비밀유지",
        "standard_text": "갑과 을은 본 계약의 이행 과정에서 알게 된 상대방의 기술상, 경영상의 정보를 본 계약기간 중은 물론 계약 종료 후 3년간 제3자에게 누설하거나 본 계약 이외의 목적으로 사용하여서는 아니 된다.",
        "is_mandatory": True,
        "industry": None,
    },
    {
        "contract_type": "service_contract",
        "clause_type": "대금지급",
        "standard_text": "갑은 을에게 계약금액 금 ○○원을 다음과 같이 지급한다. 선금: 계약 체결 시 계약금액의 30%, 중도금: 중간 검수 완료 후 30일 이내 40%, 잔금: 최종 검수 완료 후 30일 이내 30%.",
        "is_mandatory": True,
        "industry": None,
    },
    {
        "contract_type": "service_contract",
        "clause_type": "분쟁해결",
        "standard_text": "본 계약과 관련하여 발생하는 모든 분쟁은 갑과 을이 상호 협의하여 해결하도록 한다. 협의가 이루어지지 아니할 경우 서울중앙지방법원을 관할법원으로 한다.",
        "is_mandatory": True,
        "industry": None,
    },
    # NDA 표준 조항
    {
        "contract_type": "nda",
        "clause_type": "비밀정보정의",
        "standard_text": "본 계약에서 '비밀정보'란 개시 당사자가 수령 당사자에게 서면, 구두 또는 전자적 방법으로 제공하는 모든 기술적, 경영적 정보를 의미한다. 다만, 다음 각 호에 해당하는 정보는 비밀정보에서 제외한다. 1. 수령 시 이미 공지된 정보 2. 수령 당사자가 이미 보유하고 있던 정보 3. 제3자로부터 적법하게 취득한 정보",
        "is_mandatory": True,
        "industry": None,
    },
    {
        "contract_type": "nda",
        "clause_type": "비밀유지의무",
        "standard_text": "수령 당사자는 비밀정보를 본 계약에서 정한 목적으로만 사용하여야 하며, 개시 당사자의 사전 서면 동의 없이 제3자에게 공개하여서는 아니 된다. 수령 당사자는 비밀정보를 자신의 비밀정보와 동일한 수준으로 보호하여야 한다.",
        "is_mandatory": True,
        "industry": None,
    },
    # 근로계약 표준 조항
    {
        "contract_type": "employment",
        "clause_type": "근로조건",
        "standard_text": "1. 근무장소: ○○ 2. 업무내용: ○○ 3. 근로시간: 09:00~18:00 (휴게시간 12:00~13:00) 4. 근무일: 주 5일 (월~금) 5. 임금: 월 ○○원 (매월 ○일 지급) 6. 연차유급휴가: 근로기준법에 따름",
        "is_mandatory": True,
        "industry": None,
    },
    # 임대차 표준 조항
    {
        "contract_type": "lease",
        "clause_type": "보증금반환",
        "standard_text": "임대인은 임대차기간이 만료되거나 해지된 경우 임차인이 목적물을 원상회복하여 반환하는 때에 보증금을 반환한다. 임대인은 보증금에서 임차인의 미납 차임 및 관리비, 원상회복 비용을 공제할 수 있다.",
        "is_mandatory": True,
        "industry": None,
    },
]


async def ingest_sample_standard_clauses():
    """샘플 표준 계약서 조항을 DB에 삽입한다."""
    logger.info(f"표준 조항 {len(SAMPLE_STANDARD_CLAUSES)}건 삽입 시작")

    texts = [f"{c['contract_type']} {c['clause_type']} {c['standard_text']}" for c in SAMPLE_STANDARD_CLAUSES]

    try:
        embeddings = await get_embeddings_batch(texts)
    except Exception:
        logger.warning("임베딩 생성 실패. 텍스트만 삽입합니다.")
        embeddings = [None] * len(SAMPLE_STANDARD_CLAUSES)

    pool = await get_pool()

    for clause, embedding in zip(SAMPLE_STANDARD_CLAUSES, embeddings):
        try:
            if embedding:
                await pool.execute(
                    """
                    INSERT INTO standard_clauses
                        (contract_type, industry, clause_type, standard_text, is_mandatory, embedding)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    clause["contract_type"], clause.get("industry"),
                    clause["clause_type"], clause["standard_text"],
                    clause["is_mandatory"], json.dumps(embedding),
                )
            else:
                await pool.execute(
                    """
                    INSERT INTO standard_clauses
                        (contract_type, industry, clause_type, standard_text, is_mandatory)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    clause["contract_type"], clause.get("industry"),
                    clause["clause_type"], clause["standard_text"],
                    clause["is_mandatory"],
                )
            logger.info(f"  ✓ {clause['contract_type']} - {clause['clause_type']}")
        except Exception as e:
            logger.error(f"  ✗ {clause['contract_type']} - {clause['clause_type']}: {e}")

    await close_pool()
    logger.info("표준 조항 삽입 완료")


if __name__ == "__main__":
    asyncio.run(ingest_sample_standard_clauses())
