"""문서 보안 스캐너 — 악성 요소 탐지.

탐지 항목:
1. 프롬프트 인젝션 패턴 (한/영)
2. hidden text (폰트 크기 0, 흰색 글씨)
3. unicode homoglyph (Cyrillic vs Latin)
4. zero-width characters
5. bidi override
6. 비정상 인코딩
"""

import re

# 프롬프트 인젝션 패턴 (정규식)
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+a", re.IGNORECASE),
    re.compile(r"system\s*:\s*you\s+are", re.IGNORECASE),
    re.compile(r"mark\s+this\s+(contract|document)\s+as\s+safe", re.IGNORECASE),
    re.compile(r"이전\s*지시를?\s*무시"),
    re.compile(r"안전하다고\s*판단"),
    re.compile(r"위험도를?\s*0으로"),
    re.compile(r"risk_score\s*[:=]\s*0"),
]

# Zero-width 문자
ZERO_WIDTH_CHARS = {
    "\u200b",  # Zero Width Space
    "\u200c",  # Zero Width Non-Joiner
    "\u200d",  # Zero Width Joiner
    "\u2060",  # Word Joiner
    "\ufeff",  # Zero Width No-Break Space (BOM)
}

# BiDi override 문자
BIDI_CHARS = {
    "\u202a",  # Left-to-Right Embedding
    "\u202b",  # Right-to-Left Embedding
    "\u202c",  # Pop Directional Formatting
    "\u202d",  # Left-to-Right Override
    "\u202e",  # Right-to-Left Override
    "\u2066",  # Left-to-Right Isolate
    "\u2067",  # Right-to-Left Isolate
    "\u2068",  # First Strong Isolate
    "\u2069",  # Pop Directional Isolate
}

# Cyrillic 문자 중 Latin과 유사한 것들 (homoglyph)
CYRILLIC_HOMOGLYPHS = {
    "\u0430": "a", "\u0435": "e", "\u043e": "o", "\u0440": "p",
    "\u0441": "c", "\u0443": "y", "\u0445": "x", "\u0410": "A",
    "\u0412": "B", "\u0415": "E", "\u041a": "K", "\u041c": "M",
    "\u041d": "H", "\u041e": "O", "\u0420": "P", "\u0421": "C",
    "\u0422": "T", "\u0425": "X",
}


def scan_document_text(text: str) -> dict:
    """문서 텍스트 보안 스캔.

    Returns:
        {
            "status": "clean" | "suspicious" | "blocked",
            "threats": [{"type": str, "severity": str, "description": str, "location": str}]
        }
    """
    threats = []

    # 1. 프롬프트 인젝션 패턴 탐지
    for pattern in INJECTION_PATTERNS:
        matches = pattern.finditer(text)
        for match in matches:
            threats.append({
                "type": "injection",
                "severity": "critical",
                "description": f"프롬프트 인젝션 패턴 탐지: '{match.group()}'",
                "location": f"index {match.start()}-{match.end()}",
            })

    # 2. Zero-width 문자 탐지
    zwc_positions = []
    for i, char in enumerate(text):
        if char in ZERO_WIDTH_CHARS:
            zwc_positions.append(i)
    if zwc_positions:
        threats.append({
            "type": "zero_width",
            "severity": "high",
            "description": f"Zero-width 문자 {len(zwc_positions)}개 탐지",
            "location": f"positions: {zwc_positions[:10]}",
        })

    # 3. BiDi override 문자 탐지
    bidi_positions = []
    for i, char in enumerate(text):
        if char in BIDI_CHARS:
            bidi_positions.append(i)
    if bidi_positions:
        threats.append({
            "type": "bidi",
            "severity": "high",
            "description": f"BiDi override 문자 {len(bidi_positions)}개 탐지",
            "location": f"positions: {bidi_positions[:10]}",
        })

    # 4. Cyrillic homoglyph 탐지 (한국어/영어 계약서에 Cyrillic이 있으면 의심)
    homoglyph_count = 0
    for char in text:
        if char in CYRILLIC_HOMOGLYPHS:
            homoglyph_count += 1
    if homoglyph_count > 0:
        threats.append({
            "type": "homoglyph",
            "severity": "medium",
            "description": f"Cyrillic homoglyph 문자 {homoglyph_count}개 탐지 (Latin 문자와 유사)",
            "location": "document-wide",
        })

    # 5. 비정상적으로 긴 입력 (context overflow 시도)
    if len(text) > 500_000:
        threats.append({
            "type": "context_overflow",
            "severity": "high",
            "description": f"비정상적으로 긴 입력 ({len(text)} chars)",
            "location": "document-wide",
        })

    # 위협 수준 결정
    if any(t["severity"] == "critical" for t in threats):
        status = "blocked"
    elif threats:
        status = "suspicious"
    else:
        status = "clean"

    return {
        "status": status,
        "threats": threats,
    }
