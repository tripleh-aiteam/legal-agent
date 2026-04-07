"""법률 조문 조회 API."""

import re
from urllib.parse import quote

from fastapi import APIRouter, HTTPException

from app.utils.db_client import fetch, fetchrow

router = APIRouter()

# "민법 제398조" 같은 패턴에서 법률명과 조번호 추출
_LAW_REF = re.compile(
    r"(.+?)\s*제\s*(\d+)\s*조"
)

# 법률 약칭 → 정식 명칭 매핑
_LAW_ALIASES = {
    "약관규제법": "약관의 규제에 관한 법률",
    "근로기준법": "근로기준법",
    "주임법": "주택임대차보호법",
    "주택임대차법": "주택임대차보호법",
    "상임법": "상가건물 임대차보호법",
    "상가임대차법": "상가건물 임대차보호법",
    "하도급법": "하도급거래 공정화에 관한 법률",
    "공정거래법": "독점규제 및 공정거래에 관한 법률",
    "전자상거래법": "전자상거래 등에서의 소비자보호에 관한 법률",
    "정보통신망법": "정보통신망 이용촉진 및 정보보호 등에 관한 법률",
    "부정경쟁방지법": "부정경쟁방지 및 영업비밀보호에 관한 법률",
    "개인정보보호법": "개인정보 보호법",
    "소프트웨어진흥법": "소프트웨어 진흥법",
}


@router.get("/lookup")
async def lookup_law(ref: str):
    """법률 조문 조회.

    ?ref=민법 제398조 → 해당 조문 내용 반환
    """
    match = _LAW_REF.search(ref)
    if not match:
        raise HTTPException(status_code=400, detail="잘못된 법률 참조 형식입니다. 예: 민법 제398조")

    raw_name = match.group(1).strip()
    law_name = _LAW_ALIASES.get(raw_name, raw_name)
    article = f"제{match.group(2)}조"

    row = await fetchrow(
        "SELECT law_name, article_number, article_title, content "
        "FROM laws "
        "WHERE law_name LIKE $1 AND article_number = $2",
        f"%{law_name}%", article,
    )

    article_num = match.group(2)
    law_url = _build_law_url(law_name, article_num)

    if row:
        return {
            "found": True,
            "law_name": row["law_name"],
            "article_number": row["article_number"],
            "article_title": row.get("article_title", ""),
            "content": row["content"],
            "law_url": law_url,
        }

    # DB에 없어도 법령 사이트 링크는 제공
    return {
        "found": False,
        "law_name": law_name,
        "article_number": article,
        "content": None,
        "law_url": law_url,
        "message": f"'{law_name} {article}'이(가) 법령 DB에 등록되어 있지 않습니다.",
    }


def _build_law_url(law_name: str, article_num: str) -> str:
    """국가법령정보센터 조문 URL 생성."""
    encoded_name = quote(law_name, safe="")
    return (
        f"https://www.law.go.kr/법령/{encoded_name}"
        f"/%EC%A0%9C{article_num}%EC%A1%B0"
    )
