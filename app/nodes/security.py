"""security_scan 노드 — 문서 보안 스캔.

업로드된 문서에서 악성 요소를 탐지한다:
- hidden text (폰트 크기 0, hidden 속성)
- 프롬프트 인젝션 패턴
- unicode homoglyph
- zero-width characters
- bidi override
"""

from app.state.review_state import ReviewState


def security_scan(state: ReviewState) -> dict:
    """문서 보안 스캔 노드.

    TODO: Phase 3에서 document_scanner.py 연동하여 상세 구현
    """
    raw_text = state.get("raw_text", "")

    if not raw_text:
        return {
            "security_result": {"status": "clean", "threats": []},
            "security_status": "clean",
        }

    # Phase 3에서 상세 구현할 보안 검사 호출
    from app.security.document_scanner import scan_document_text

    result = scan_document_text(raw_text)

    return {
        "security_result": result,
        "security_status": result.get("status", "clean"),
    }
