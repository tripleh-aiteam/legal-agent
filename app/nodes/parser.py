"""parse_document 노드 — 문서 파싱 + 조항 분리.

PDF/DOCX 텍스트 추출 후 조항 단위로 분리한다.
"""

from app.parsers.clause_splitter import split_clauses
from app.state.review_state import ReviewState


def parse_document(state: ReviewState) -> dict:
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

    # 문서 유형 추론 (간단한 키워드 기반)
    doc_type = _infer_doc_type(raw_text)

    # 당사자 추출 (간단한 패턴 매칭)
    parties = _extract_parties(raw_text)

    return {
        "clauses": clauses,
        "doc_type": doc_type,
        "parties": parties,
        "language": language,
    }


def _infer_doc_type(text: str) -> str | None:
    """문서 유형 추론."""
    text_lower = text[:2000].lower()

    type_keywords = {
        "service_contract": ["용역", "수급", "발주", "납품", "검수"],
        "nda": ["비밀유지", "기밀", "confidential", "non-disclosure"],
        "employment": ["근로계약", "근로자", "사용자", "임금", "근무시간"],
        "lease": ["임대차", "임대인", "임차인", "보증금", "월세", "임대료"],
    }

    for doc_type, keywords in type_keywords.items():
        if any(kw in text_lower for kw in keywords):
            return doc_type

    return None


def _extract_parties(text: str) -> list[str]:
    """당사자 추출."""
    import re

    parties = []

    # "갑: ...", "을: ..." 패턴
    gap_pattern = re.compile(r"[\"']?갑[\"']?\s*[:：]\s*(.+?)[\n,]")
    eul_pattern = re.compile(r"[\"']?을[\"']?\s*[:：]\s*(.+?)[\n,]")

    gap_match = gap_pattern.search(text[:3000])
    eul_match = eul_pattern.search(text[:3000])

    if gap_match:
        parties.append(gap_match.group(1).strip())
    if eul_match:
        parties.append(eul_match.group(1).strip())

    return parties
