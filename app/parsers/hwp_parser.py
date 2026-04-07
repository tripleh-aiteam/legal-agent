"""HWP/HWPX 파서 — 한글 문서 텍스트 추출.

- HWP (한/글 97~): OLE2 컨테이너, BodyText/Section* 스트림에서 텍스트 추출
- HWPX (한/글 2014+): ZIP 컨테이너, Contents/section*.xml에서 텍스트 추출
"""

import io
import logging
import struct
import xml.etree.ElementTree as ET
import zlib
import zipfile

import olefile

logger = logging.getLogger(__name__)

# HWP 텍스트 레코드 태그 (HWPTAG_PARA_TEXT = 67)
_HWPTAG_PARA_TEXT = 67


def _is_hwpx(file_bytes: bytes) -> bool:
    """HWPX(ZIP 기반) 파일인지 확인."""
    return file_bytes[:4] == b"PK\x03\x04"


def _extract_hwpx_text(file_bytes: bytes) -> str:
    """HWPX 파일에서 텍스트 추출.

    HWPX는 ZIP 컨테이너로, Contents/section*.xml에 본문이 있다.
    """
    texts = []

    with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
        # section 파일 목록 (정렬)
        section_files = sorted(
            [n for n in zf.namelist() if n.startswith("Contents/section") and n.endswith(".xml")]
        )

        if not section_files:
            # 다른 경로 시도
            section_files = sorted(
                [n for n in zf.namelist() if "section" in n.lower() and n.endswith(".xml")]
            )

        for section_file in section_files:
            try:
                xml_data = zf.read(section_file)
                root = ET.fromstring(xml_data)
                # 모든 텍스트 노드 추출
                _collect_xml_text(root, texts)
            except Exception:
                logger.warning("HWPX 섹션 파싱 실패: %s", section_file, exc_info=True)

    return "\n".join(texts)


def _collect_xml_text(element: ET.Element, texts: list[str]) -> None:
    """XML 엘리먼트에서 재귀적으로 텍스트를 수집."""
    # 네임스페이스 무시하고 태그명만 비교
    tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag

    if tag == "t" or tag == "text":
        if element.text:
            texts.append(element.text)
    elif tag == "p" or tag == "para":
        # 문단 단위로 개행 추가
        para_texts = []
        for child in element:
            child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if child_tag == "run":
                for sub in child:
                    sub_tag = sub.tag.split("}")[-1] if "}" in sub.tag else sub.tag
                    if sub_tag == "t" and sub.text:
                        para_texts.append(sub.text)
            elif child_tag == "t" and child.text:
                para_texts.append(child.text)
        if para_texts:
            texts.append("".join(para_texts))
        return  # 하위 재귀 방지

    for child in element:
        _collect_xml_text(child, texts)


def _extract_hwp_text(file_bytes: bytes) -> str:
    """HWP(OLE2) 파일에서 텍스트 추출.

    HWP 파일 구조:
    - FileHeader: 파일 정보 (압축 여부 등)
    - BodyText/Section0, Section1, ...: 본문 데이터
    - 각 섹션은 레코드 스트림으로 구성
    """
    ole = olefile.OleFileIO(io.BytesIO(file_bytes))
    texts = []

    try:
        # FileHeader에서 압축 여부 확인
        header_data = ole.openstream("FileHeader").read()
        # 바이트 36의 비트0: 압축 여부
        is_compressed = bool(header_data[36] & 1)

        # BodyText 섹션들 읽기
        section_idx = 0
        while True:
            stream_name = f"BodyText/Section{section_idx}"
            if not ole.exists(stream_name):
                break

            data = ole.openstream(stream_name).read()

            if is_compressed:
                try:
                    data = zlib.decompress(data, -15)
                except zlib.error:
                    logger.warning("섹션 %d 압축 해제 실패", section_idx)
                    section_idx += 1
                    continue

            # 레코드 스트림에서 텍스트 추출
            section_text = _parse_hwp_records(data)
            texts.append(section_text)
            section_idx += 1

    except Exception:
        logger.error("HWP 파일 파싱 실패", exc_info=True)
    finally:
        ole.close()

    return "\n".join(texts)


def _parse_hwp_records(data: bytes) -> str:
    """HWP 레코드 스트림에서 텍스트를 추출한다.

    레코드 헤더: 4바이트
      - 비트 0~9: 태그 ID
      - 비트 10~19: 레벨
      - 비트 20~31: 데이터 길이 (0xFFF이면 다음 4바이트가 실제 길이)
    """
    texts = []
    offset = 0

    while offset < len(data) - 4:
        try:
            header = struct.unpack_from("<I", data, offset)[0]
            tag_id = header & 0x3FF
            size = (header >> 20) & 0xFFF
            offset += 4

            if size == 0xFFF:
                if offset + 4 > len(data):
                    break
                size = struct.unpack_from("<I", data, offset)[0]
                offset += 4

            if offset + size > len(data):
                break

            record_data = data[offset: offset + size]
            offset += size

            if tag_id == _HWPTAG_PARA_TEXT:
                text = _decode_para_text(record_data)
                if text.strip():
                    texts.append(text)

        except (struct.error, IndexError):
            break

    return "\n".join(texts)


def _decode_para_text(data: bytes) -> str:
    """HWP 문단 텍스트 레코드를 디코딩한다.

    UTF-16LE 인코딩, 특수 제어 문자 처리.
    """
    chars = []
    i = 0

    while i < len(data) - 1:
        code = struct.unpack_from("<H", data, i)[0]
        i += 2

        if code == 0:
            break
        elif code < 32:
            # 제어 문자: 인라인 데이터 스킵
            if code in (1, 2, 3, 11, 12, 13, 14, 15, 16, 17, 18, 21, 22, 23):
                i += 12  # 추가 데이터 12바이트 스킵
            elif code == 10:
                chars.append("\n")  # 줄바꿈
            elif code == 24:
                i += 14
            elif code == 9:
                chars.append("\t")  # 탭
        else:
            chars.append(chr(code))

    return "".join(chars)


def extract_text_from_hwp_bytes(file_bytes: bytes) -> dict:
    """HWP 또는 HWPX 바이트에서 텍스트를 추출한다."""
    if _is_hwpx(file_bytes):
        text = _extract_hwpx_text(file_bytes)
        file_type = "hwpx"
    else:
        text = _extract_hwp_text(file_bytes)
        file_type = "hwp"

    # 페이지 수 추정 (한국어 기준 ~1500자/페이지)
    page_count = max(1, len(text) // 1500)

    return {
        "text": text,
        "pages": [text],  # HWP는 페이지 구분이 어려움
        "page_count": page_count,
        "ocr_used": False,
        "file_type": file_type,
    }
