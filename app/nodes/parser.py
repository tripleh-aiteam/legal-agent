"""parse_document 노드 — 문서 파싱 + 조항 분리.

PDF/DOCX 텍스트 추출 후 조항 단위로 분리한다.
"""

import logging
import re

from app.config import settings
from app.llm.client import call_llm_json
from app.parsers.clause_splitter import split_clauses
from app.state.review_state import ReviewState

logger = logging.getLogger(__name__)


async def parse_document(state: ReviewState) -> dict:
    """문서를 파싱하고 조항을 분리하는 노드.

    입력: raw_text (이미 추출된 텍스트)
    출력: clauses, doc_type, parties, language
    """
    raw_text = state.get("raw_text", "")
    language = state.get("language", "ko")

    if not raw_text:
        return {
            "clauses": [],
            "doc_type": None,
            "parties": [],
            "error": "문서 텍스트가 비어있습니다.",
        }

    # 조항 분리
    clauses = split_clauses(raw_text, language=language)

    # 문서 유형 추론 (LLM 기반, 폴백: 키워드)
    doc_type_result = await _infer_doc_type_llm(raw_text)

    # 당사자 추출 (간단한 패턴 매칭)
    parties = _extract_parties(raw_text)

    return {
        "clauses": clauses,
        "doc_type": doc_type_result["doc_type"],
        "doc_type_label": doc_type_result.get("doc_type_label"),
        "parties": parties,
        "language": language,
    }


async def _infer_doc_type_llm(text: str) -> dict:
    """LLM으로 문서 유형을 자유롭게 분류. 하드코딩된 목록에 의존하지 않음."""
    text_sample = text[:2000]

    try:
        result = await call_llm_json(
            model=settings.classifier_model,
            system_prompt=(
                "계약서 텍스트를 읽고 문서 유형을 분류하세요. "
                "JSON으로만 응답: "
                '{\"doc_type\": \"유형 코드(영어 snake_case)\", '
                '\"doc_type_label\": \"유형 이름(한국어)\", '
                '\"confidence\": 0.0~1.0}\n\n'
                "예시 유형 코드: sales(매매), lease(임대차), service_contract(용역), "
                "nda(비밀유지), employment(근로), franchise(가맹), "
                "investment(투자), joint_venture(합작), loan(대출/차용), "
                "license(라이선스), distribution(유통/대리점), construction(공사/건설), "
                "consulting(자문/컨설팅), settlement(합의/화해) 등.\n"
                "위 목록에 없으면 적절한 코드를 만들어도 됩니다."
            ),
            user_prompt=f"다음 계약서의 유형을 분류하세요:\n\n{text_sample}",
            max_tokens=256,
            temperature=0.0,
        )
        data = result["data"]
        doc_type = data.get("doc_type")
        label = data.get("doc_type_label", "")
        confidence = data.get("confidence", 0)
        logger.info(f"문서 유형 분류: {doc_type} ({label}), 신뢰도: {confidence}")
        return {"doc_type": doc_type, "doc_type_label": label}
    except Exception as e:
        logger.warning(f"LLM 문서 유형 분류 실패, 키워드 폴백: {e}")
        doc_type = _infer_doc_type_keyword(text)
        return {"doc_type": doc_type, "doc_type_label": None}


def _infer_doc_type_keyword(text: str) -> str | None:
    """키워드 기반 폴백 분류."""
    text_sample = text[:3000]

    type_keywords: dict[str, list[tuple[str, int]]] = {
        "sales": [
            ("매매", 5), ("매도인", 5), ("매수인", 5), ("매매대금", 5),
            ("소유권이전", 4), ("잔금", 3), ("중도금", 3),
        ],
        "lease": [
            ("임대차", 5), ("임대인", 5), ("임차인", 5), ("월세", 5),
            ("임대료", 4), ("전세", 4),
        ],
        "service_contract": [
            ("용역", 5), ("수급", 4), ("발주", 4), ("납품", 3), ("검수", 3),
        ],
        "nda": [
            ("비밀유지", 5), ("기밀", 4), ("confidential", 4),
        ],
        "employment": [
            ("근로계약", 5), ("근로자", 4), ("임금", 3), ("근무시간", 4),
        ],
    }

    scores: dict[str, int] = {}
    for doc_type, keywords in type_keywords.items():
        score = sum(weight for kw, weight in keywords if kw in text_sample)
        if score > 0:
            scores[doc_type] = score

    if not scores:
        return None

    return max(scores, key=scores.get)  # type: ignore[arg-type]


def _extract_parties(text: str) -> list[str]:
    """당사자 추출."""
    parties = []

    gap_pattern = re.compile(r"[\"']?갑[\"']?\s*[:：]\s*(.+?)[\n,]")
    eul_pattern = re.compile(r"[\"']?을[\"']?\s*[:：]\s*(.+?)[\n,]")

    gap_match = gap_pattern.search(text[:3000])
    eul_match = eul_pattern.search(text[:3000])

    if gap_match:
        parties.append(gap_match.group(1).strip())
    if eul_match:
        parties.append(eul_match.group(1).strip())

    return parties
