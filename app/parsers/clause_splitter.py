"""조항 분리기 — 계약서를 조항 단위로 분리.

한국어/영어 계약서 패턴 지원.
"""

import re

# 한국어 조항 패턴
KO_PATTERNS = [
    re.compile(r"제\s*(\d+)\s*조\s*[\(（]([^)）]+)[\)）]"),   # 제1조 (목적)
    re.compile(r"제\s*(\d+)\s*조\s+([^\n]+)"),                 # 제1조 목적
    re.compile(r"제\s*(\d+)\s*조"),                             # 제1조
]

# 영어 조항 패턴
EN_PATTERNS = [
    re.compile(
        r"(?:Section|Article|SECTION|ARTICLE)\s+(\d+(?:\.\d+)?)\s*[:\.]?\s*([^\n]*)",
        re.IGNORECASE,
    ),
    re.compile(r"^(\d+)\.\s+([A-Z][^\n]*)", re.MULTILINE),
]


def split_clauses(text: str, language: str = "ko") -> list[dict]:
    """텍스트를 조항 단위로 분리.

    Args:
        text: 원문 텍스트
        language: "ko" (한국어) | "en" (영어)

    Returns:
        [
            {
                "clause_number": "제1조",
                "title": "목적",
                "content": "본 계약은...",
                "start_index": 0,
                "end_index": 150,
            },
            ...
        ]
    """
    patterns = KO_PATTERNS if language == "ko" else EN_PATTERNS

    # 모든 패턴으로 조항 시작 위치 탐색
    matches = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            matches.append({
                "start": match.start(),
                "number": match.group(1) if match.lastindex >= 1 else "",
                "title": match.group(2).strip() if match.lastindex >= 2 else "",
                "raw_match": match.group(0),
            })

    if not matches:
        # 조항 패턴을 찾지 못한 경우: 전체를 하나의 조항으로
        return [{
            "clause_number": None,
            "title": None,
            "content": text.strip(),
            "start_index": 0,
            "end_index": len(text),
        }]

    # 위치 기준 정렬 + 중복 제거
    matches.sort(key=lambda m: m["start"])
    matches = _deduplicate_matches(matches)

    # 조항 내용 추출 (현재 매치 ~ 다음 매치 사이)
    clauses = []
    for i, match in enumerate(matches):
        start = match["start"]
        end = matches[i + 1]["start"] if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()

        clause_number = (
            f"제{match['number']}조" if language == "ko" else f"Article {match['number']}"
        )

        clauses.append({
            "clause_number": clause_number,
            "title": match["title"] or None,
            "content": content,
            "start_index": start,
            "end_index": end,
        })

    return clauses


def _deduplicate_matches(matches: list[dict], threshold: int = 10) -> list[dict]:
    """겹치는 매치 제거 (같은 조항이 여러 패턴에 매칭될 수 있음)."""
    if not matches:
        return matches

    deduped = [matches[0]]
    for match in matches[1:]:
        if abs(match["start"] - deduped[-1]["start"]) > threshold:
            deduped.append(match)

    return deduped
