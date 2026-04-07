"""조항 분리기 테스트."""

from app.parsers.clause_splitter import split_clauses


class TestKoreanClauseSplitter:
    """한국어 조항 분리 테스트."""

    def test_standard_format(self):
        """표준 형식: 제N조 (제목)"""
        text = """
제1조 (목적)
본 계약은 갑과 을 사이의 용역 계약에 관한 사항을 정한다.

제2조 (용역의 범위)
을은 다음 각 호의 용역을 수행한다.
1. 웹 애플리케이션 개발
2. 유지보수 서비스

제3조 (계약기간)
본 계약의 기간은 2026년 1월 1일부터 2026년 12월 31일까지로 한다.
"""
        clauses = split_clauses(text, language="ko")

        assert len(clauses) == 3
        assert clauses[0]["clause_number"] == "제1조"
        assert clauses[0]["title"] == "목적"
        assert "용역 계약" in clauses[0]["content"]
        assert clauses[1]["clause_number"] == "제2조"
        assert clauses[2]["clause_number"] == "제3조"

    def test_no_parentheses_title(self):
        """괄호 없는 형식: 제N조 제목"""
        text = """
제1조 목적
본 계약은 목적을 정한다.

제2조 용역의 범위
을은 용역을 수행한다.
"""
        clauses = split_clauses(text, language="ko")

        assert len(clauses) == 2
        assert clauses[0]["clause_number"] == "제1조"

    def test_no_clauses_found(self):
        """조항 패턴이 없는 텍스트."""
        text = "이것은 조항이 없는 일반 텍스트입니다."
        clauses = split_clauses(text, language="ko")

        assert len(clauses) == 1
        assert clauses[0]["clause_number"] is None

    def test_fullwidth_parentheses(self):
        """전각 괄호 형식: 제N조（제목）"""
        text = """
제1조（목적）
본 계약의 목적을 정한다.

제2조（정의）
본 계약에서 사용하는 용어의 정의는 다음과 같다.
"""
        clauses = split_clauses(text, language="ko")

        assert len(clauses) == 2
        assert clauses[0]["title"] == "목적"


class TestEnglishClauseSplitter:
    """영어 조항 분리 테스트."""

    def test_section_format(self):
        """Section N. Title 형식."""
        text = """
Section 1. Purpose
This agreement sets forth the terms.

Section 2. Scope of Services
The Provider shall perform the following services.

Section 3. Term
This Agreement shall commence on January 1, 2026.
"""
        clauses = split_clauses(text, language="en")

        assert len(clauses) == 3
        assert clauses[0]["clause_number"] == "Article 1"

    def test_article_format(self):
        """Article N: Title 형식."""
        text = """
Article 1: Definitions
The following terms shall have the meanings set forth below.

Article 2: Obligations
Each party shall perform its obligations.
"""
        clauses = split_clauses(text, language="en")

        assert len(clauses) == 2


class TestClauseSplitterEdgeCases:
    """엣지 케이스 테스트."""

    def test_empty_text(self):
        """빈 텍스트."""
        clauses = split_clauses("", language="ko")
        assert len(clauses) == 1

    def test_single_clause(self):
        """단일 조항."""
        text = "제1조 (목적)\n본 계약의 목적을 정한다."
        clauses = split_clauses(text, language="ko")
        assert len(clauses) == 1
        assert clauses[0]["clause_number"] == "제1조"
