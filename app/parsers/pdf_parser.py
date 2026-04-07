"""PDF 파서 — pdfplumber + OCR 하이브리드 텍스트 추출.

한국어 계약서 PDF 특화:
- 2단 컬럼(영문/한국어 병렬) 레이아웃 자동 감지
- 폰트 인코딩이 깨진 한국어 텍스트 감지 → OCR 자동 전환
- 스캔 PDF OCR 폴백
"""

import io
import logging
import os
import re

import fitz  # PyMuPDF (OCR용)
import pdfplumber

from app.config import settings

logger = logging.getLogger(__name__)

# 한국어 유니코드 범위 (가-힣 + 자모)
_KO_CHAR = re.compile(r"[\uAC00-\uD7AF\u3130-\u318F]")
# 의미 있는 문자 (알파벳, 한국어, 숫자)
_MEANINGFUL = re.compile(r"[\w\uAC00-\uD7AF]")


def _has_korean(text: str) -> bool:
    """텍스트에 한국어 유니코드가 포함되어 있는지 확인."""
    return bool(_KO_CHAR.search(text))


_COMMON_EN_WORDS = {
    "the", "of", "and", "to", "in", "is", "that", "for", "it", "with",
    "as", "was", "on", "are", "be", "by", "this", "an", "or", "from",
    "not", "but", "have", "has", "shall", "will", "any", "all", "may",
    "which", "their", "such", "other", "its", "between", "under",
    "article", "section", "agreement", "contract", "party", "company",
}


def _is_garbled(text: str) -> bool:
    """텍스트가 깨졌는지 감지.

    한국어 PDF에서 폰트 인코딩이 잘못되면 한국어 글자가
    의미없는 라틴 문자 조합으로 추출됨 (예: 'BWIY ws - at QL').
    정상적인 영어 텍스트와 구분하기 위해 영어 단어 출현도 확인.
    """
    if len(text.strip()) < 30:
        return False

    ko_chars = len(_KO_CHAR.findall(text))
    if ko_chars > 0:
        # 한국어 유니코드가 있으면 깨진 게 아님
        return False

    # 한국어가 전혀 없는 텍스트: 정상 영어인지 깨진 한국어인지 판별
    words = text.lower().split()
    if not words:
        return True

    en_word_count = sum(1 for w in words if w.strip(".,;:()\"'") in _COMMON_EN_WORDS)
    en_ratio = en_word_count / len(words)

    # 영어 비율이 10% 이상이면 정상 영어 텍스트
    if en_ratio >= 0.10:
        return False

    # 영어 비율이 매우 낮고 텍스트가 길면 → 깨진 한국어
    return len(text.strip()) > 50


def _ocr_page_full(fitz_page, lang: str = "kor+eng") -> str:
    """PyMuPDF 페이지 전체를 OCR 처리."""
    from PIL import Image
    import pytesseract

    pix = fitz_page.get_pixmap(dpi=300)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return pytesseract.image_to_string(img, lang=lang)


def _ocr_page_region(fitz_page, bbox: tuple, lang: str = "kor+eng") -> str:
    """PyMuPDF 페이지의 특정 영역을 OCR 처리.

    bbox: (x0, y0, x1, y1) 좌표 (포인트 단위)
    """
    from PIL import Image
    import pytesseract

    clip = fitz.Rect(*bbox)
    pix = fitz_page.get_pixmap(dpi=300, clip=clip)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return pytesseract.image_to_string(img, lang=lang)


def _is_dual_column(page) -> bool:
    """페이지가 2단 레이아웃인지 감지."""
    words = page.extract_words(x_tolerance=2, y_tolerance=2)
    if len(words) < 10:
        return False

    width = page.width
    mid = width / 2
    margin = width * 0.08

    center_words = [
        w for w in words if mid - margin < (w["x0"] + w["x1"]) / 2 < mid + margin
    ]

    center_ratio = len(center_words) / len(words)
    return center_ratio < 0.15


def _extract_page_smart(plumber_page, fitz_page, page_num: int) -> tuple[str, bool]:
    """페이지에서 텍스트를 스마트하게 추출.

    1) pdfplumber로 텍스트 추출 시도
    2) 깨진 텍스트 감지 시 OCR 전환
    3) 2단 레이아웃이면 컬럼별 처리

    Returns:
        (text, ocr_used)
    """
    ocr_used = False

    if _is_dual_column(plumber_page):
        # 2단 레이아웃: 좌/우 컬럼 분리
        width = plumber_page.width
        height = plumber_page.height
        mid = width / 2

        left_crop = plumber_page.within_bbox((0, 0, mid, height), relative=False)
        right_crop = plumber_page.within_bbox((mid, 0, width, height), relative=False)

        left_text = left_crop.extract_text(x_tolerance=2, y_tolerance=2) or ""
        right_text = right_crop.extract_text(x_tolerance=2, y_tolerance=2) or ""

        # 각 컬럼이 깨졌는지 확인, 깨졌으면 OCR
        if _is_garbled(left_text) and settings.ocr_enabled:
            logger.info("페이지 %d 좌측 컬럼 텍스트 깨짐 감지 → OCR 전환", page_num)
            # pdfplumber 좌표 → PyMuPDF 좌표 (동일 단위: 포인트)
            left_text = _ocr_page_region(
                fitz_page, (0, 0, mid * 72 / 72, height * 72 / 72), lang=settings.ocr_language
            )
            ocr_used = True

        if _is_garbled(right_text) and settings.ocr_enabled:
            logger.info("페이지 %d 우측 컬럼 텍스트 깨짐 감지 → OCR 전환", page_num)
            right_text = _ocr_page_region(
                fitz_page, (mid, 0, width, height), lang=settings.ocr_language
            )
            ocr_used = True

        # 한국어 컬럼 판별 및 우선 배치
        left_ko = _has_korean(left_text)
        right_ko = _has_korean(right_text)

        if left_ko and right_ko:
            text = f"{left_text}\n{right_text}"
        elif left_ko and not right_ko:
            text = f"{left_text}\n\n--- 영문 원문 ---\n{right_text}"
        elif right_ko and not left_ko:
            text = f"{right_text}\n\n--- 영문 원문 ---\n{left_text}"
        else:
            text = f"{left_text}\n{right_text}"

    else:
        # 단일 컬럼
        text = plumber_page.extract_text(x_tolerance=2, y_tolerance=2) or ""

        if _is_garbled(text) and settings.ocr_enabled:
            logger.info("페이지 %d 텍스트 깨짐 감지 → OCR 전환", page_num)
            text = _ocr_page_full(fitz_page, lang=settings.ocr_language)
            ocr_used = True
        elif not text.strip() and settings.ocr_enabled:
            # 텍스트가 전혀 없는 스캔 PDF
            logger.info("페이지 %d 텍스트 없음 → OCR 전환", page_num)
            text = _ocr_page_full(fitz_page, lang=settings.ocr_language)
            ocr_used = True

    return text, ocr_used


def _extract_all_pages(file_bytes: bytes = None, file_path: str = None) -> dict:
    """PDF에서 모든 페이지 텍스트를 추출한다."""
    ocr_used = False

    # TESSDATA_PREFIX 환경변수 설정
    tessdata = os.environ.get("TESSDATA_PREFIX")
    if tessdata:
        os.environ["TESSDATA_PREFIX"] = tessdata

    # pdfplumber + PyMuPDF 동시 오픈
    if file_bytes:
        plumber_pdf = pdfplumber.open(io.BytesIO(file_bytes))
        fitz_doc = fitz.open(stream=file_bytes, filetype="pdf")
    else:
        plumber_pdf = pdfplumber.open(file_path)
        fitz_doc = fitz.open(file_path)

    pages = []
    try:
        for i, plumber_page in enumerate(plumber_pdf.pages):
            fitz_page = fitz_doc[i]
            try:
                text, page_ocr = _extract_page_smart(plumber_page, fitz_page, i + 1)
                if page_ocr:
                    ocr_used = True
                pages.append(text)
            except Exception:
                logger.warning("페이지 %d 추출 실패, 기본 방식 시도", i + 1, exc_info=True)
                text = plumber_page.extract_text() or ""
                pages.append(text)
    finally:
        plumber_pdf.close()
        fitz_doc.close()

    return {
        "text": "\n".join(pages),
        "pages": pages,
        "page_count": len(pages),
        "ocr_used": ocr_used,
    }


def extract_text_from_pdf(file_path: str) -> dict:
    """PDF 파일에서 텍스트를 추출한다."""
    return _extract_all_pages(file_path=file_path)


def extract_text_from_pdf_bytes(file_bytes: bytes) -> dict:
    """PDF 바이트에서 텍스트를 추출한다."""
    return _extract_all_pages(file_bytes=file_bytes)
