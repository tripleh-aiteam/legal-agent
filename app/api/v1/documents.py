"""문서 업로드/조회 API."""

import json
import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, UploadFile

from app.config import settings
from app.llm.client import get_embeddings_batch
from app.models.document import DocumentSchema, DocumentUploadResponse
from app.parsers.clause_splitter import split_clauses
from app.parsers.docx_parser import extract_text_from_docx_bytes
from app.parsers.hwp_parser import extract_text_from_hwp_bytes
from app.parsers.pdf_parser import extract_text_from_pdf_bytes
from app.security.document_scanner import scan_document_text
from app.utils.db_client import execute, fetch, fetchrow

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile,
    doc_type: str | None = None,
    language: str = "ko",
):
    """문서 업로드 (PDF/DOCX).

    파이프라인: Upload → Parse → SecurityScan → ClauseSplit → Embedding → DB
    """
    # 파일 타입 검증
    filename = file.filename or ""
    lower_name = filename.lower()
    if lower_name.endswith(".pdf"):
        file_type = "pdf"
    elif lower_name.endswith(".docx"):
        file_type = "docx"
    elif lower_name.endswith(".hwp") or lower_name.endswith(".hwpx"):
        file_type = "hwp"
    else:
        raise HTTPException(status_code=400, detail="PDF, DOCX, HWP, HWPX 파일을 지원합니다.")

    # 파일 크기 검증
    contents = await file.read()
    if len(contents) > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"파일 크기가 {settings.max_file_size_mb}MB를 초과합니다.",
        )

    # 텍스트 추출
    if file_type == "pdf":
        parse_result = extract_text_from_pdf_bytes(contents)
    elif file_type == "hwp":
        parse_result = extract_text_from_hwp_bytes(contents)
    else:
        parse_result = extract_text_from_docx_bytes(contents)

    raw_text = parse_result.get("text", "")
    # 서로게이트 문자 제거 (PDF 파서에서 깨진 한글이 포함될 수 있음)
    raw_text = raw_text.encode("utf-8", errors="surrogatepass").decode("utf-8", errors="replace")
    page_count = parse_result.get("page_count", 0)

    if not raw_text.strip():
        raise HTTPException(
            status_code=400,
            detail="문서에서 텍스트를 추출할 수 없습니다. "
                   "스캔 PDF의 경우 Tesseract OCR 설치가 필요합니다.",
        )

    # 보안 스캔
    security_result = scan_document_text(raw_text)
    security_status = security_result["status"]

    if security_status == "blocked":
        raise HTTPException(
            status_code=400,
            detail=f"보안 위험이 탐지되어 업로드가 차단되었습니다: "
                   f"{[t['description'] for t in security_result['threats']]}",
        )

    # 조항 분리
    clauses = split_clauses(raw_text, language=language)

    # DB 저장: 문서
    doc_row = await fetchrow(
        """
        INSERT INTO documents
            (file_name, file_type, file_size, storage_path, raw_text,
             clause_count, page_count, language, doc_type,
             security_scan_status, security_scan_result, status)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 'parsed')
        RETURNING id
        """,
        filename, file_type, len(contents), f"/uploads/{filename}",
        raw_text, len(clauses), page_count, language, doc_type,
        security_status, json.dumps(security_result),
    )
    document_id = doc_row["id"]

    # DB 저장: 조항 + 임베딩
    clause_texts = [c.get("content", "")[:500] for c in clauses]
    try:
        embeddings = await get_embeddings_batch(clause_texts)
    except Exception:
        logger.warning("임베딩 생성 실패. 임베딩 없이 저장합니다.")
        embeddings = [None] * len(clauses)

    for clause, embedding in zip(clauses, embeddings):
        if embedding:
            await execute(
                """
                INSERT INTO clauses
                    (document_id, clause_number, title, content,
                     start_index, end_index, embedding)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                document_id, clause.get("clause_number"), clause.get("title"),
                clause.get("content", ""),
                clause.get("start_index"), clause.get("end_index"),
                json.dumps(embedding),
            )
        else:
            await execute(
                """
                INSERT INTO clauses
                    (document_id, clause_number, title, content,
                     start_index, end_index)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                document_id, clause.get("clause_number"), clause.get("title"),
                clause.get("content", ""),
                clause.get("start_index"), clause.get("end_index"),
            )

    return DocumentUploadResponse(
        document_id=document_id,
        file_name=filename,
        status="parsed",
        clause_count=len(clauses),
        page_count=page_count,
        message=f"문서 업로드 완료. {len(clauses)}개 조항 식별.",
    )


@router.get("/{document_id}")
async def get_document(document_id: UUID):
    """문서 및 조항 정보 조회."""
    doc = await fetchrow(
        "SELECT * FROM documents WHERE id = $1", str(document_id)
    )
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")

    clauses = await fetch(
        "SELECT clause_number, title, content FROM clauses WHERE document_id = $1 ORDER BY start_index",
        str(document_id),
    )

    return {
        "id": str(doc["id"]),
        "file_name": doc["file_name"],
        "file_type": doc["file_type"],
        "status": doc["status"],
        "clause_count": doc["clause_count"],
        "page_count": doc["page_count"],
        "language": doc["language"],
        "doc_type": doc["doc_type"],
        "security_scan_status": doc["security_scan_status"],
        "raw_text": doc["raw_text"],
        "clauses": [dict(c) for c in clauses],
    }
