# Legal Review Agent — Advanced Architecture

> 단순 LLM 호출이 아닌, 스스로 검증하고 보강하는 멀티 에이전트 시스템
> **v2.0** — Drafter Agent, Advisor Agent 추가

---

## 1. 전체 구조 Overview

### 1.1 서비스 3가지 모드

```
┌─────────────────────────────────────────────────────────────┐
│                                                              │
│   모드 1: 생성 (Draft)                                       │
│   "계약서 없어, 만들어줘"                                     │
│   → Drafter Agent → Analyzer → Validator → 최종 계약서       │
│                                                              │
│   모드 2: 분석 (Review)                                      │
│   "이 계약서 검토해줘"                                        │
│   → Analyzer Agent → Validator → 분석 리포트                 │
│                                                              │
│   모드 3: 상담 (Advise)                                      │
│   "이 조항 싸인해도 돼? 좀 찝찝한데"                           │
│   → Advisor Agent (대화형) → 실시간 답변                     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 전체 에이전트 맵

```
                         사용자 요청
                            │
                            ▼
                ┌───────────────────────┐
                │   🎯 Orchestrator      │
                │   (오케스트레이터)       │
                │                       │
                │   역할:               │
                │   - 요청 분류 (3모드)   │
                │   - 에이전트 라우팅     │
                │   - 결과 취합          │
                │   - 최종 품질 판단     │
                └──────────┬────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    ┌────▼────┐      ┌────▼────┐      ┌────▼────┐
    │ Mode 1  │      │ Mode 2  │      │ Mode 3  │
    │ 생성    │      │ 분석    │      │ 상담    │
    └────┬────┘      └────┬────┘      └────┬────┘
         │                │                │
         ▼                ▼                ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐
    │📝Drafter │   │🔍Analyzer│   │💬Advisor │
    │  Agent   │   │  Agent   │   │  Agent   │
    └────┬─────┘   └────┬─────┘   └────┬─────┘
         │              │              │
         └──────┬───────┘              │
                │                      │
    ┌───────────┼──────────────┐       │
    │           │              │       │
    ▼           ▼              ▼       ▼
┌────────┐ ┌────────┐  ┌────────┐ ┌────────┐
│📚 RAG  │ │🛡️Secur-│  │✅Valid-│ │📚 RAG  │
│ Agent  │ │ity     │  │ator   │ │ Agent  │
│        │ │Agent   │  │Agent  │ │(실시간)│
└────────┘ └────────┘  └────────┘ └────────┘

       (공유 인프라)          (공유 인프라)
```

---

## 2. 각 에이전트 상세 설계

### 2.1 Orchestrator (오케스트레이터)

전체 플로우를 관장하는 메인 에이전트. 사용자 요청을 받아 어떤 에이전트들을 어떤 순서로 호출할지 결정한다.

```python
class Orchestrator:
    """
    핵심 역할:
    1. 요청 분류 (Intent Classification)
       - "이 계약서 검토해줘" → full_review 파이프라인
       - "제8조가 불리한지 봐줘" → single_clause 분석
       - "이전 버전이랑 비교해줘" → comparison 파이프라인
       - "이 조항 관련 판례 찾아줘" → precedent_search

    2. 파이프라인 실행
       - 각 파이프라인은 어떤 에이전트를 어떤 순서로 호출할지 정의
       - 병렬 실행 가능한 건 병렬로 (Analyzer + RAG 동시)

    3. 결과 취합 및 품질 판단
       - Validator의 검증 결과에 따라 재시도 여부 결정
       - 최대 재시도 횟수 초과 시 경고와 함께 반환
    """

    MAX_RETRIES = 2

    async def handle(self, request: ReviewRequest) -> ReviewResponse:

        # ── Step 0: Security 선검사 ──
        security_result = await self.security_agent.scan_document(request.document)
        if security_result.threat_level == "blocked":
            return ReviewResponse(
                status="blocked",
                reason=security_result.threats
            )

        # ── Step 1: 요청 분류 ──
        intent = await self._classify_intent(request)

        # ── Step 2: 파이프라인 선택 & 실행 ──
        pipeline = self._get_pipeline(intent)

        for attempt in range(self.MAX_RETRIES + 1):

            # Analyzer + RAG 병렬 실행
            analyzer_result, rag_result = await asyncio.gather(
                self.analyzer_agent.analyze(request, pipeline),
                self.rag_agent.retrieve(request, pipeline),
            )

            # RAG 결과를 Analyzer 결과에 병합 (근거 보강)
            enriched_result = self._merge_results(analyzer_result, rag_result)

            # ── Step 3: 검증 ──
            validation = await self.validator_agent.validate(
                result=enriched_result,
                original_document=request.document,
                rag_context=rag_result,
            )

            if validation.passed:
                return enriched_result

            # 검증 실패 시: 실패 사유를 피드백으로 넘겨서 재분석
            request.feedback = validation.issues
            request.attempt = attempt + 1

        # 최대 재시도 초과: 경고와 함께 반환
        enriched_result.warnings.append(
            "일부 항목의 검증이 완료되지 않았습니다. 전문가 검토를 권장합니다."
        )
        return enriched_result
```

### 2.2 Analyzer Agent (분석 에이전트)

계약서를 읽고 위험 조항을 찾아내는 핵심 에이전트.

```python
class AnalyzerAgent:
    """
    분석 전략:

    1. 조항별 독립 분석 (Clause-level)
       - 각 조항을 개별적으로 분석 → 세부 위험 식별
       - 조항 간 상호참조 관계도 파악 ("제3조에 따라" → 제3조도 같이 봄)

    2. 문서 전체 분석 (Document-level)
       - 전체 계약서의 균형성 평가 (갑-을 간 권리/의무 비율)
       - 빠진 표준 조항 탐지 (손해배상 한도, 분쟁해결, 비밀유지 등)

    3. 관점 기반 분석 (Perspective-aware)
       - perspective="을" → 을에게 불리한 조항 집중 탐지
       - perspective="갑" → 갑의 리스크 관점에서 분석
       - perspective="neutral" → 양측 균형 평가

    4. 재시도 시 피드백 반영
       - Validator가 "제8조 인용이 원문과 다름"이라고 했으면
       - 해당 조항만 다시 분석 (전체 재분석 X → 비용 절감)
    """

    async def analyze(self, request, pipeline) -> AnalysisResult:

        document = request.document
        clauses = request.clauses

        # ── 재시도인 경우: 피드백 반영 ──
        if request.feedback:
            return await self._retry_with_feedback(request)

        # ── 1단계: 조항별 분석 (병렬) ──
        clause_tasks = []
        for clause in clauses:
            task = self._analyze_single_clause(
                clause=clause,
                full_context=document.raw_text,  # 전체 맥락 참고
                perspective=request.perspective,
            )
            clause_tasks.append(task)

        clause_results = await asyncio.gather(*clause_tasks)

        # ── 2단계: 문서 전체 분석 ──
        doc_level = await self._analyze_document_level(
            clauses=clauses,
            clause_results=clause_results,
            perspective=request.perspective,
        )

        # ── 3단계: 결과 통합 ──
        return self._compile_results(clause_results, doc_level)

    async def _analyze_single_clause(self, clause, full_context, perspective):
        """
        개별 조항 분석.

        프롬프트 구조:
        - System: 법률 분석가 역할 + 출력 JSON 스키마
        - User: [전체 계약서 요약] + [이 조항 원문] + [관점 지시]

        중요: 전체 맥락을 요약해서 같이 넘긴다.
        "제3조에 따라"가 나오면 제3조가 뭔지 알아야 하니까.
        """
        pass

    async def _analyze_document_level(self, clauses, clause_results, perspective):
        """
        문서 전체 수준 분석.

        검사 항목:
        1. 누락 조항 체크 (체크리스트 기반)
           - 계약 유형별 필수 조항 목록과 대조
           - 예: 용역계약인데 납품 검수 조항이 없음 → 경고

        2. 갑-을 균형성 분석
           - 해지권: 갑만 있는지, 양측 다 있는지
           - 손해배상: 한쪽만 부담하는지
           - 비밀유지: 편면적인지 쌍무적인지

        3. 위험도 종합 점수 산출
           - clause_results의 개별 severity를 가중 합산
           - critical=10, high=7, medium=4, low=1
        """
        pass

    async def _retry_with_feedback(self, request):
        """
        Validator 피드백을 반영한 부분 재분석.

        전체를 다시 하지 않고, 문제가 있던 조항만 재분석한다.
        피드백 내용을 프롬프트에 포함:
        "이전 분석에서 다음 오류가 발견되었습니다: [피드백].
         해당 부분을 수정하여 다시 분석해주세요."
        """
        pass
```

### 2.3 RAG Agent (법률 근거 에이전트)

법률 조문과 판례를 검색하여 분석에 근거를 부여하는 에이전트.

```python
class RAGAgent:
    """
    ★ 이 에이전트가 있어야 "민법 제393조에 따르면..." 같은
      근거 있는 분석이 가능해진다.

    데이터 소스:
    1. 법령 DB (국가법령정보센터 API → Supabase pgvector)
       - 민법, 상법, 약관규제법, 근로기준법 등 핵심 법률
       - 조문 단위로 임베딩
       - 정기 업데이트 (법 개정 반영)

    2. 판례 DB (공공데이터포털 판례 API → Supabase pgvector)
       - 계약 분쟁 관련 판례
       - 판결 요지 + 핵심 판시사항 임베딩

    3. 표준 계약서 DB (AI Hub 계약 서식 데이터)
       - 업종/유형별 표준 계약서 조항
       - "이 조항이 업계 표준과 얼마나 다른지" 비교 기준

    검색 전략:
    - Hybrid Search: 벡터 유사도 + 키워드 매칭 결합
    - 벡터만 쓰면 "민법 제393조"를 정확히 못 찾을 수 있음
    - 키워드로 법률명+조번호 매칭 + 벡터로 의미 유사도 보강
    """

    async def retrieve(self, request, pipeline) -> RAGResult:

        clauses = request.clauses

        # ── 1단계: 분석 대상 조항에서 검색 쿼리 생성 ──
        queries = await self._generate_queries(clauses, request.perspective)

        # ── 2단계: 3개 소스에서 병렬 검색 ──
        results = await asyncio.gather(
            self._search_laws(queries),           # 법령 검색
            self._search_precedents(queries),     # 판례 검색
            self._search_standard_clauses(queries), # 표준 계약서 검색
        )

        law_results, precedent_results, standard_results = results

        # ── 3단계: Reranking ──
        # 검색 결과를 관련성 기준으로 재정렬
        # Cross-encoder 모델 또는 LLM 기반 reranking
        reranked = await self._rerank(
            queries=queries,
            candidates=[*law_results, *precedent_results, *standard_results],
        )

        return RAGResult(
            laws=law_results,
            precedents=precedent_results,
            standards=standard_results,
            reranked_top_k=reranked[:20],  # 상위 20개
        )

    async def _generate_queries(self, clauses, perspective):
        """
        조항에서 검색 쿼리를 자동 생성한다.

        예시:
        조항: "을은 갑에게 발생한 일체의 손해를 배상한다"
        →
        생성되는 쿼리들:
        1. "무제한 손해배상 조항 유효성" (의미 검색용)
        2. "민법 제393조" (법률 키워드 검색용)
        3. "약관규제법 손해배상 불공정" (관련 법률 검색용)
        4. "손해배상 한도 미설정 판례" (판례 검색용)

        하나의 조항에서 여러 쿼리를 생성하는 이유:
        - 벡터 검색은 다양한 표현으로 검색해야 recall이 높음
        - 법률 번호 기반 검색과 의미 기반 검색을 모두 커버
        """
        pass

    async def _search_laws(self, queries) -> list:
        """
        법령 DB에서 관련 법률 조문을 검색한다.

        검색 방법: Hybrid Search
        1. pgvector cosine similarity (의미 검색)
        2. Full-text search on 법률명 + 조번호 (키워드 검색)
        3. 두 결과를 RRF (Reciprocal Rank Fusion)로 통합

        SQL 예시:
        SELECT *,
               (1 - (embedding <=> query_embedding)) as vector_score,
               ts_rank(to_tsvector('korean', content),
                       plainto_tsquery('korean', '손해배상 한도')) as text_score,
               -- RRF score
               (1.0 / (60 + vector_rank)) + (1.0 / (60 + text_rank)) as rrf_score
        FROM laws
        ORDER BY rrf_score DESC
        LIMIT 10;
        """
        pass

    async def _search_precedents(self, queries) -> list:
        """
        판례 DB에서 유사 판례를 검색한다.

        반환 형식:
        {
            "case_number": "2023다54321",
            "court": "대법원",
            "date": "2023-08-15",
            "summary": "...",
            "relevant_part": "...",  ← 쿼리와 가장 관련 높은 부분 추출
            "similarity_score": 0.89
        }
        """
        pass

    async def _search_standard_clauses(self, queries) -> list:
        """
        표준 계약서에서 해당 유형의 표준 조항을 검색한다.

        용도: "이 조항이 업계 표준과 얼마나 다른지" 비교 근거
        예: 용역계약 표준 손해배상 조항 vs 현재 계약서 조항
        """
        pass

    async def _rerank(self, queries, candidates) -> list:
        """
        검색 결과를 재정렬한다.

        방법 1: Cross-encoder (정확하지만 느림)
        방법 2: LLM에게 "이 중 가장 관련 높은 순서로 정렬해" (간단)
        방법 3: Cohere rerank API (추천 — 빠르고 정확)
        """
        pass
```

### 2.4 Security Agent (보안 에이전트)

이전 스펙의 Security Layer를 에이전트로 승격. 문서 입력부터 최종 출력까지 전 과정을 감시한다.

```python
class SecurityAgent:
    """
    기존 스펙의 document_scanner, prompt_guard, output_validator,
    data_sanitizer, audit_logger를 하나의 에이전트로 통합.

    다른 에이전트와의 차이점:
    - 다른 에이전트는 "분석"을 하지만, Security Agent는 "감시"를 한다
    - 모든 다른 에이전트의 입출력을 검사할 수 있는 권한
    - 위협 탐지 시 파이프라인 자체를 중단시킬 수 있음

    작동 시점:
    1. Pre-processing: 문서 업로드 시 악성 요소 스캔
    2. In-processing: LLM 프롬프트 구성 시 인젝션 방어
    3. Post-processing: LLM 출력에서 PII 유출/이상 탐지
    """

    async def scan_document(self, document) -> SecurityResult:
        """업로드 시점 보안 검사 (이전 스펙의 DocumentScanner)"""
        pass

    async def guard_prompt(self, prompt) -> GuardedPrompt:
        """LLM 호출 전 프롬프트 보안 처리 (이전 스펙의 PromptGuard)"""
        pass

    async def validate_output(self, output, original) -> OutputValidation:
        """LLM 출력 보안 검증 (이전 스펙의 OutputValidator)"""
        pass

    async def monitor_pipeline(self, event) -> None:
        """파이프라인 전체 이벤트 모니터링 및 감사 로깅"""
        pass
```

### 2.5 Validator Agent (검증 에이전트) ★ 핵심

분석 결과를 **독립적으로** 검증하는 에이전트. 이게 에이전트 품질의 핵심이다.

```python
class ValidatorAgent:
    """
    ★ 가장 중요한 에이전트.
    ★ Analyzer가 "맞다"고 한 걸, 별도의 LLM 호출로 "정말 맞나?" 확인한다.

    핵심 원칙:
    - Analyzer와 다른 LLM 모델을 사용한다 (교차 검증)
      예: Analyzer가 Claude면, Validator는 GPT 사용 (또는 반대)
    - 검증은 생성보다 쉽다 → 저렴한 모델로도 충분
    - 검증 실패 시 구체적인 피드백을 생성하여 Orchestrator에 반환

    검증 항목 (5단계):
    """

    # Analyzer와 다른 모델 사용 (교차 검증)
    VALIDATOR_MODEL = "gpt-4o-mini"  # Analyzer가 Claude면 이걸 씀

    async def validate(self, result, original_document, rag_context) -> ValidationResult:

        issues = []

        # ── Check 1: 원문 크로스체크 ──
        # finding의 original_text가 실제 원문에 존재하는지
        text_issues = await self._check_original_text(
            findings=result.findings,
            original=original_document.raw_text,
        )
        issues.extend(text_issues)

        # ── Check 2: 법률 조항 실존 확인 ──
        # "민법 제393조"가 실제로 존재하고, 인용 내용이 맞는지
        # RAG DB에서 해당 조문을 직접 조회하여 대조
        law_issues = await self._verify_law_references(
            findings=result.findings,
            law_db=rag_context.laws,
        )
        issues.extend(law_issues)

        # ── Check 3: 판례 실존 확인 ──
        # 인용된 판례 번호가 실제 존재하는지 DB 조회
        precedent_issues = await self._verify_precedents(
            findings=result.findings,
            precedent_db=rag_context.precedents,
        )
        issues.extend(precedent_issues)

        # ── Check 4: 논리적 일관성 ──
        # overall_risk_score와 개별 severity 간 모순 없는지
        # 수정 제안이 원래 문제를 실제로 해결하는지
        logic_issues = await self._check_logical_consistency(
            result=result,
        )
        issues.extend(logic_issues)

        # ── Check 5: 교차 검증 (LLM 기반) ──
        # 별도 LLM에게 "이 분석이 맞나?" 물어봄
        # 가장 비용이 높은 검증이므로 위 4개를 먼저 하고
        # 위에서 문제가 없을 때만 실행 (비용 절감)
        if not issues:
            cross_issues = await self._cross_validate_with_llm(
                result=result,
                original=original_document,
            )
            issues.extend(cross_issues)

        return ValidationResult(
            passed=len(issues) == 0,
            issues=issues,
            confidence=self._calculate_confidence(result, issues),
        )

    async def _check_original_text(self, findings, original) -> list:
        """
        각 finding의 original_text가 원문에 실제로 있는지 확인.

        단순 string match가 아니라 fuzzy matching 사용.
        이유: LLM이 원문을 약간 바꿔서 인용할 수 있음
             (띄어쓰기, 조사 차이 등)

        매칭 기준: similarity >= 0.85 (rapidfuzz 사용)
        실패 시: {"type": "text_mismatch", "finding_id": "...", "detail": "..."}
        """
        pass

    async def _verify_law_references(self, findings, law_db) -> list:
        """
        인용된 법률 조항이 실제 존재하는지 RAG DB에서 조회.

        검증 단계:
        1. 법률명 + 조번호 파싱 ("민법 제393조" → law="민법", article=393)
        2. DB에서 해당 조문 조회
        3. 조문이 존재하면 → finding의 설명과 실제 조문 내용 대조
        4. 조문이 없으면 → 할루시네이션으로 판정

        이게 있어야 "LLM이 없는 법률을 만들어내는" 문제를 막을 수 있다.
        """
        pass

    async def _verify_precedents(self, findings, precedent_db) -> list:
        """
        인용된 판례가 실제 존재하는지 확인.

        판례번호 형식: "2023다54321", "2024나12345" 등
        DB에 없는 경우: 국가법령정보 API로 실시간 조회 시도
        그래도 없으면: 할루시네이션으로 판정
        """
        pass

    async def _check_logical_consistency(self, result) -> list:
        """
        논리적 모순 탐지.

        규칙 기반 검증:
        1. severity가 전부 "low"인데 overall_risk_score > 5 → 모순
        2. severity가 "critical"인데 overall_risk_score < 3 → 모순
        3. suggested_text가 original_text와 동일 → 의미 없는 수정
        4. suggestion_reason이 실제 수정 내용과 관련 없음 → 불일치
        5. 같은 조항에 대해 모순되는 findings → 중복/모순
        """
        pass

    async def _cross_validate_with_llm(self, result, original) -> list:
        """
        ★ 별도 LLM으로 교차 검증.

        Analyzer가 Claude로 분석했으면, 여기서는 GPT-4o-mini를 사용.
        (같은 모델은 같은 실수를 반복할 수 있으므로)

        프롬프트:
        "다음은 AI가 계약서를 분석한 결과입니다.
         이 분석에서 잘못된 점이 있는지 검증해주세요.
         특히 다음을 확인하세요:
         1. 위험으로 판단한 조항이 실제로 위험한지
         2. 수정 제안이 법적으로 유효한지
         3. 놓친 중요한 위험 조항이 있는지"

        비용: 이 검증은 비싸므로 앞선 4개 검증을 모두 통과한 경우에만 실행
        """
        pass

    def _calculate_confidence(self, result, issues) -> float:
        """
        최종 신뢰도 점수 계산.

        공식:
        base_confidence = mean(finding.confidence_score for finding in findings)
        penalty = len(issues) * 0.1
        final = max(0, base_confidence - penalty)

        이 점수가 0.7 미만이면 "전문가 검토 권장" 경고 추가
        """
        pass
```

---

## 3. RAG 파이프라인 상세 설계

### 3.1 데이터 수집 & 인덱싱 파이프라인

```
┌─────────────────────────────────────────────────────────┐
│                 Data Ingestion Pipeline                   │
│                 (정기 실행: 주 1회)                        │
│                                                          │
│  ┌─────────────┐    ┌──────────┐    ┌──────────────┐    │
│  │ 국가법령정보 │    │ 공공데이터│    │   AI Hub     │    │
│  │ 센터 API    │    │ 판례 API │    │ 법률 데이터   │    │
│  │ (법령 조문)  │    │ (판례)   │    │ (계약서 서식) │    │
│  └──────┬──────┘    └─────┬────┘    └──────┬───────┘    │
│         │                 │                │             │
│         ▼                 ▼                ▼             │
│  ┌──────────────────────────────────────────────┐       │
│  │              Text Preprocessor                │       │
│  │                                               │       │
│  │  1. 텍스트 정제 (HTML 태그 제거, 인코딩 통일) │       │
│  │  2. 청킹 (법률: 조문 단위, 판례: 판시사항 단위)│       │
│  │  3. 메타데이터 추출 (법률명, 조번호, 시행일 등)│       │
│  └──────────────────┬───────────────────────────┘       │
│                     │                                    │
│                     ▼                                    │
│  ┌──────────────────────────────────────────────┐       │
│  │              Embedding Generator              │       │
│  │                                               │       │
│  │  Model: text-embedding-3-small (1536 dim)     │       │
│  │  Batch: 100 chunks per request                │       │
│  │  Rate limit: 3000 RPM                         │       │
│  └──────────────────┬───────────────────────────┘       │
│                     │                                    │
│                     ▼                                    │
│  ┌──────────────────────────────────────────────┐       │
│  │         Supabase pgvector Storage             │       │
│  │                                               │       │
│  │  laws          → 법률 조문 임베딩              │       │
│  │  precedents    → 판례 요지 임베딩              │       │
│  │  standard_docs → 표준 계약서 조항 임베딩       │       │
│  └──────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────┘
```

### 3.2 검색 시 플로우 (Query Time)

```
사용자 계약서의 "제8조 손해배상" 조항
            │
            ▼
┌───────────────────────────────────┐
│      Query Generator (LLM)       │
│                                   │
│  입력: 조항 원문                   │
│  출력: 검색 쿼리 3~5개            │
│                                   │
│  예시 출력:                       │
│  q1: "손해배상 범위 한도 미설정"    │
│  q2: "민법 제393조 손해배상"       │
│  q3: "약관규제법 제8조 불공정"     │
│  q4: "무제한 배상 판례"           │
└──────────┬────────────────────────┘
           │
     ┌─────┴─────┐
     │           │
     ▼           ▼
┌─────────┐ ┌─────────┐
│ Vector  │ │Keyword  │
│ Search  │ │ Search  │
│(pgvector│ │(ts_rank)│
│ cosine) │ │         │
└────┬────┘ └────┬────┘
     │           │
     ▼           ▼
┌───────────────────────────────────┐
│   RRF (Reciprocal Rank Fusion)   │
│                                   │
│   score = Σ (1 / (k + rank_i))   │
│   k = 60 (smoothing factor)      │
│                                   │
│   벡터와 키워드 결과를 통합 정렬   │
└──────────┬────────────────────────┘
           │
           ▼
┌───────────────────────────────────┐
│          Reranker                 │
│                                   │
│  Cohere rerank 또는               │
│  Cross-encoder 모델로             │
│  최종 관련성 재정렬               │
│                                   │
│  Top-K: 법령 5개, 판례 5개,      │
│         표준조항 3개              │
└──────────┬────────────────────────┘
           │
           ▼
    Analyzer Agent에 전달
    (분석 시 근거로 사용)
```

### 3.3 RAG 데이터 스키마

```sql
-- 법령 조문 테이블 (국가법령정보센터 데이터)
CREATE TABLE laws (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 법령 식별
    law_id TEXT NOT NULL,            -- 법령 ID (API 기준)
    law_name TEXT NOT NULL,          -- "민법", "상법" 등
    article_number TEXT NOT NULL,    -- "제393조", "제8조" 등
    article_title TEXT,              -- 조항 제목

    -- 내용
    content TEXT NOT NULL,           -- 조문 전문

    -- 메타데이터
    enforcement_date DATE,           -- 시행일
    last_amended_date DATE,          -- 최종 개정일
    category TEXT,                   -- "민사", "상사", "노동" 등

    -- 검색용
    embedding vector(1536),
    search_tokens tsvector GENERATED ALWAYS AS (
        to_tsvector('korean', law_name || ' ' || article_number || ' ' || content)
    ) STORED,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(law_id, article_number)
);

-- 판례 테이블 (공공데이터포털 + 법원 API 데이터)
CREATE TABLE precedents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 판례 식별
    case_number TEXT NOT NULL UNIQUE,   -- "2023다54321"
    court TEXT NOT NULL,                -- "대법원", "서울고등법원" 등
    decision_date DATE,
    case_type TEXT,                     -- "민사", "형사", "행정" 등

    -- 내용
    title TEXT NOT NULL,
    summary TEXT NOT NULL,              -- 판결 요지
    key_points TEXT,                    -- 핵심 판시사항
    full_text TEXT,                     -- 전문 (있는 경우)

    -- 분류
    category TEXT,                      -- "계약", "손해배상", "해지" 등
    related_laws TEXT[],                -- ["민법 제393조", "약관규제법 제8조"]
    tags TEXT[] DEFAULT '{}',

    -- 검색용
    embedding vector(1536),
    search_tokens tsvector GENERATED ALWAYS AS (
        to_tsvector('korean', case_number || ' ' || title || ' ' || summary)
    ) STORED,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 표준 계약서 조항 테이블 (AI Hub 데이터)
CREATE TABLE standard_clauses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 계약 유형
    contract_type TEXT NOT NULL,        -- "용역계약", "임대차", "NDA", etc.
    industry TEXT,                      -- "IT", "건설", "제조" 등

    -- 조항 정보
    clause_type TEXT NOT NULL,          -- "손해배상", "해지", "비밀유지" 등
    standard_text TEXT NOT NULL,        -- 표준 조항 전문

    -- 기준 정보
    is_mandatory BOOLEAN DEFAULT false, -- 필수 포함 조항인지
    typical_range JSONB,                -- 예: {"배상한도": "계약금액의 100~200%"}

    -- 검색용
    embedding vector(1536),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Hybrid Search용 인덱스
CREATE INDEX idx_laws_embedding ON laws USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_laws_search ON laws USING gin (search_tokens);
CREATE INDEX idx_precedents_embedding ON precedents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_precedents_search ON precedents USING gin (search_tokens);
CREATE INDEX idx_standard_embedding ON standard_clauses USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);

-- Hybrid Search 함수
CREATE OR REPLACE FUNCTION hybrid_search_laws(
    query_embedding vector(1536),
    query_text TEXT,
    match_count INT DEFAULT 10,
    vector_weight FLOAT DEFAULT 0.7,
    text_weight FLOAT DEFAULT 0.3
)
RETURNS TABLE (
    id UUID,
    law_name TEXT,
    article_number TEXT,
    content TEXT,
    vector_score FLOAT,
    text_score FLOAT,
    combined_score FLOAT
)
LANGUAGE sql
AS $$
    WITH vector_results AS (
        SELECT id, 1 - (embedding <=> query_embedding) as score,
               ROW_NUMBER() OVER (ORDER BY embedding <=> query_embedding) as rank
        FROM laws
        ORDER BY embedding <=> query_embedding
        LIMIT match_count * 2
    ),
    text_results AS (
        SELECT id, ts_rank(search_tokens, plainto_tsquery('korean', query_text)) as score,
               ROW_NUMBER() OVER (ORDER BY ts_rank(search_tokens, plainto_tsquery('korean', query_text)) DESC) as rank
        FROM laws
        WHERE search_tokens @@ plainto_tsquery('korean', query_text)
        LIMIT match_count * 2
    ),
    rrf AS (
        SELECT
            COALESCE(v.id, t.id) as id,
            COALESCE(1.0 / (60 + v.rank), 0) * vector_weight as v_score,
            COALESCE(1.0 / (60 + t.rank), 0) * text_weight as t_score
        FROM vector_results v
        FULL OUTER JOIN text_results t ON v.id = t.id
    )
    SELECT
        l.id, l.law_name, l.article_number, l.content,
        r.v_score as vector_score,
        r.t_score as text_score,
        (r.v_score + r.t_score) as combined_score
    FROM rrf r
    JOIN laws l ON r.id = l.id
    ORDER BY combined_score DESC
    LIMIT match_count;
$$;
```

---

## 4. 전체 파이프라인 플로우 (End-to-End)

```
사용자: "이 계약서 을 관점에서 검토해줘"
│
▼
[1] Orchestrator: 요청 수신 & 분류
│   → intent: "full_review"
│   → perspective: "을"
│
▼
[2] Security Agent: 문서 보안 스캔
│   → hidden text? ❌
│   → injection? ❌
│   → malicious payload? ❌
│   → result: CLEAN ✅
│
▼
[3] Document Parser: 텍스트 추출 & 조항 분리
│   → 23개 조항 식별
│   → 당사자: 주식회사 AAA(갑), 주식회사 BBB(을)
│
▼
[4] 병렬 실행:
│
├─→ [4a] Analyzer Agent: 조항별 위험 분석
│   │   → 제8조: critical (무제한 손해배상)
│   │   → 제12조: high (일방적 해지권)
│   │   → 제15조: medium (과도한 경업금지)
│   │   → overall_risk_score: 7.2
│   │
│   └─→ 수정안 생성 (각 위험 조항별)
│
└─→ [4b] RAG Agent: 법률 근거 검색
    │   → 민법 제393조 (손해배상의 범위) 조회
    │   → 약관규제법 제8조 (손해배상액 예정) 조회
    │   → 2023다54321 판례 (배상한도 미설정 무효) 조회
    │   → 용역계약 표준 손해배상 조항 조회
    │
    └─→ Reranking → Top-K 선별
│
▼
[5] Orchestrator: 결과 병합
│   → Analyzer 결과에 RAG 근거 연결
│   → 제8조 위험 → 근거: 민법 제393조 + 2023다54321 판례
│
▼
[6] Validator Agent: 5단계 검증
│   ├─ Check 1: original_text 원문 대조 ✅
│   ├─ Check 2: "민법 제393조" 실존 확인 ✅
│   ├─ Check 3: "2023다54321" 판례 실존 확인 ✅
│   ├─ Check 4: 논리적 일관성 (7.2점 & critical 존재 = 일관) ✅
│   └─ Check 5: GPT-4o-mini 교차 검증 ✅
│
│   → validation: PASSED ✅
│   → confidence: 0.91
│
▼
[7] 최종 응답 반환
│
│   {
│     "overall_risk_score": 7.2,
│     "confidence": 0.91,
│     "risk_summary": "본 계약서는 을에게 불리한 조항이 다수...",
│     "findings": [
│       {
│         "severity": "critical",
│         "title": "손해배상 한도 미설정",
│         "original_text": "을은 ... 일체의 손해를 배상한다",
│         "suggested_text": "을은 ... 직접 손해를 배상하되, 총액은 ...",
│         "legal_basis": {
│           "law": "민법 제393조 (손해배상의 범위)",
│           "precedent": "2023다54321 - 배상한도 미설정 무효 판결"
│         },
│         "confidence_score": 0.92
│       }
│     ],
│     "validation": {
│       "all_checks_passed": true,
│       "cross_validated": true,
│       "validator_model": "gpt-4o-mini"
│     }
│   }
│
▼
사용자에게 결과 표시
```

---

## 5. 검증 실패 시 재시도 플로우

```
[6] Validator: Check 2 실패!
│   → "민법 제395조" 존재하지 않음 (실제로는 제393조)
│   → issue: {"type": "law_not_found", "claimed": "민법 제395조"}
│
▼
[6-retry] Orchestrator: 재분석 지시
│   → feedback: "제8조 분석에서 '민법 제395조'를 인용했으나 존재하지 않음.
│                올바른 법률 조항을 확인하여 수정하세요."
│   → 전체 재분석이 아닌, 해당 finding만 재분석 (비용 절감)
│
▼
[4a-retry] Analyzer: 피드백 반영 재분석
│   → 제8조 재분석 → "민법 제393조"로 수정
│
▼
[6-retry] Validator: 재검증
│   → Check 2: "민법 제393조" 실존 확인 ✅
│   → PASSED ✅
│
▼
[7] 최종 응답 반환 (수정된 버전)
```

---

## 6. 비용 최적화 전략

```
┌────────────────────────────────────────────────────┐
│                비용 최적화 전략                       │
│                                                     │
│  에이전트별 모델 배정:                               │
│                                                     │
│  Orchestrator  → GPT-4o-mini (저렴, 분류만 하면 됨)  │
│  Analyzer      → Claude Sonnet (메인 분석, 균형)     │
│  RAG Agent     → 쿼리 생성만 LLM, 검색은 DB         │
│  Validator     → GPT-4o-mini (검증은 생성보다 쉬움)   │
│  Security      → 규칙 기반 우선, LLM은 최소 사용     │
│                                                     │
│  예상 비용 (10페이지 계약서 1건 기준):               │
│                                                     │
│  Orchestrator:   ~$0.002 (분류)                     │
│  Analyzer:       ~$0.05  (조항별 분석)               │
│  RAG query gen:  ~$0.005 (쿼리 생성)                │
│  RAG search:     ~$0.001 (DB 쿼리, 거의 무료)       │
│  Validator:      ~$0.01  (검증)                     │
│  Embedding:      ~$0.002 (문서 임베딩)               │
│  ─────────────────────────────                      │
│  Total:          ~$0.07/건                          │
│                                                     │
│  (Harvey는 변호사 1명당 월 $1,200)                   │
└────────────────────────────────────────────────────┘
```

---

## 7. Claude Code에게 구현 요청 순서

```
Phase 1: RAG 데이터 파이프라인
"국가법령정보센터 API에서 민법, 상법, 약관규제법, 근로기준법 조문을
 수집하고, 조문 단위로 청킹해서 임베딩 후 Supabase pgvector에
 저장하는 파이프라인을 구현해줘. hybrid_search_laws 함수도 만들어."

Phase 2: 에이전트 프레임워크
"Orchestrator, AnalyzerAgent, RAGAgent, SecurityAgent,
 ValidatorAgent 5개 에이전트의 기본 클래스와 통신 구조를 구현해줘.
 Orchestrator가 나머지를 호출하는 파이프라인 구조로."

Phase 3: Analyzer + RAG 연동
"AnalyzerAgent가 조항별 분석을 하면서, RAGAgent에서 관련 법률과
 판례를 검색해서 분석 결과에 법적 근거를 부여하는 흐름을 구현해줘."

Phase 4: Validator 구현
"ValidatorAgent의 5단계 검증을 구현해줘. 특히 법률 조항 실존 확인은
 RAG DB에서 직접 조회하고, 교차 검증은 Analyzer와 다른 LLM 모델을 써줘."

Phase 5: 재시도 루프
"Validator가 실패하면 Orchestrator가 피드백을 Analyzer에 전달해서
 해당 부분만 재분석하는 루프를 구현해줘. 최대 2회 재시도."

Phase 6: Drafter Agent
"대화형 인터뷰로 계약 정보를 수집하고, RAG에서 표준 서식을 가져와서
 맞춤 계약서를 생성하는 DrafterAgent를 구현해줘.
 생성 후 자동으로 Analyzer → Validator를 거치는 자체 검증 루프도."

Phase 7: Advisor Agent
"대화형 법률 상담 에이전트를 구현해줘. 사용자가 계약서 특정 조항에
 대해 질문하면 RAG로 근거를 찾고, 위험도 판단 + 행동 제안을 해줘.
 대화 맥락을 유지하면서 후속 질문도 처리할 수 있게."
```

---

## 8. Drafter Agent (계약서 생성 에이전트) — NEW

### 8.1 Overview

```
스타트업 대표: "프리랜서 개발자랑 3개월 용역계약 쓰려고 해"
                            │
                            ▼
               ┌───────────────────────┐
               │   📝 Drafter Agent     │
               │                       │
               │   Phase 1: 인터뷰     │
               │   (필요 정보 수집)     │
               │         │             │
               │         ▼             │
               │   Phase 2: 검색      │
               │   (표준 서식 조회)     │
               │         │             │
               │         ▼             │
               │   Phase 3: 생성      │
               │   (맞춤 계약서 작성)   │
               └──────────┬────────────┘
                          │
                          ▼
               ┌───────────────────────┐
               │   🔍 Self-Review      │
               │                       │
               │   Analyzer가 Drafter  │
               │   가 만든 계약서를     │
               │   자동으로 검토       │
               └──────────┬────────────┘
                          │
                          ▼
               ┌───────────────────────┐
               │   ✅ Validator        │
               │                       │
               │   법적 유효성 검증     │
               │   누락 조항 체크      │
               └──────────┬────────────┘
                          │
                    Pass? ─┤
                    │      │
                No ─┘      │ Yes
             (Drafter가    ▼
              수정 후     최종 계약서
              재검토)     DOCX/PDF 출력
```

### 8.2 상세 구현

```python
class DrafterAgent:
    """
    계약서가 없는 사용자를 위해 맞춤 계약서를 생성하는 에이전트.

    핵심 원칙:
    - 한번에 만들지 않고, 대화형 인터뷰로 정보를 수집한다
    - 표준 서식을 기반으로 커스터마이징한다 (from scratch가 아님)
    - 생성한 계약서를 스스로 검토한다 (Analyzer + Validator 연동)
    """

    # =============================================
    # Phase 1: 인터뷰 (정보 수집)
    # =============================================

    # 계약 유형별 필수 수집 정보
    INTERVIEW_SCHEMAS = {
        "service_contract": {  # 용역계약
            "required": [
                {
                    "field": "parties",
                    "question": "계약 당사자가 누구인가요? (회사명 또는 이름)",
                    "sub_questions": [
                        "갑 (발주자): ",
                        "을 (수급자): ",
                    ]
                },
                {
                    "field": "scope",
                    "question": "용역의 구체적인 내용은 무엇인가요?",
                    "examples": "예: 웹앱 개발, 디자인, 컨설팅 등"
                },
                {
                    "field": "duration",
                    "question": "계약 기간은 어떻게 되나요?",
                    "examples": "예: 2026.05.01 ~ 2026.07.31 (3개월)"
                },
                {
                    "field": "payment",
                    "question": "대금과 지급 조건은 어떻게 되나요?",
                    "sub_questions": [
                        "총 금액: ",
                        "지급 방식: (월별/완료 후/분할 등)",
                        "지급 시기: (매월 말일/검수 후 30일 이내 등)"
                    ]
                },
                {
                    "field": "deliverables",
                    "question": "납품물은 무엇인가요?",
                    "examples": "예: 소스코드, 디자인 파일, 보고서 등"
                },
            ],
            "optional": [
                {
                    "field": "ip_ownership",
                    "question": "결과물의 지식재산권은 누구에게 귀속되나요?",
                    "default": "갑에게 귀속 (일반적)",
                    "warning": "이 부분이 명확하지 않으면 나중에 분쟁이 많이 생깁니다."
                },
                {
                    "field": "confidentiality",
                    "question": "비밀유지 조항이 필요한가요?",
                    "default": "양측 상호 비밀유지",
                },
                {
                    "field": "termination",
                    "question": "중도 해지 조건을 어떻게 설정할까요?",
                    "default": "양측 30일 전 서면 통지",
                },
                {
                    "field": "liability",
                    "question": "손해배상 한도를 설정할까요?",
                    "default": "계약금액 한도 내 직접손해",
                    "warning": "한도를 안 정하면 을에게 매우 불리할 수 있습니다."
                },
                {
                    "field": "dispute",
                    "question": "분쟁 해결 방법은?",
                    "default": "서울중앙지방법원 관할",
                },
            ]
        },

        "nda": {  # 비밀유지계약
            "required": [
                {"field": "parties", "question": "계약 당사자는?"},
                {"field": "confidential_info", "question": "비밀정보의 범위는?"},
                {"field": "duration", "question": "비밀유지 기간은?"},
                {"field": "purpose", "question": "정보 제공 목적은?"},
            ],
            "optional": [
                {"field": "penalty", "question": "위반 시 위약금을 정할까요?"},
                {"field": "return_clause", "question": "계약 종료 시 자료 반환/파기 조건은?"},
            ]
        },

        "employment": {  # 근로계약
            "required": [
                {"field": "parties", "question": "사업장과 근로자 정보는?"},
                {"field": "position", "question": "직위와 업무 내용은?"},
                {"field": "salary", "question": "급여와 지급일은?"},
                {"field": "working_hours", "question": "근무 시간과 장소는?"},
                {"field": "duration", "question": "계약 기간은? (정규직/계약직)"},
            ],
            "optional": [
                {"field": "probation", "question": "수습 기간을 둘까요?"},
                {"field": "non_compete", "question": "경업금지 조항이 필요한가요?"},
                {"field": "benefits", "question": "복리후생 조건은?"},
            ]
        },

        "lease": {  # 임대차계약
            "required": [
                {"field": "parties", "question": "임대인과 임차인 정보는?"},
                {"field": "property", "question": "임대 대상 물건의 주소와 면적은?"},
                {"field": "rent", "question": "보증금과 월세는?"},
                {"field": "duration", "question": "임대 기간은?"},
            ],
            "optional": [
                {"field": "maintenance", "question": "수선/관리 의무 분담은?"},
                {"field": "sublease", "question": "전대 허용 여부는?"},
            ]
        },
    }

    async def start_interview(self, user_input: str) -> InterviewState:
        """
        사용자의 첫 입력으로 계약 유형을 분류하고 인터뷰를 시작한다.

        1. LLM으로 계약 유형 분류
           "프리랜서 개발자랑 계약" → service_contract
           "직원 채용" → employment
           "사무실 임대" → lease
           "NDA 작성" → nda

        2. 첫 입력에서 이미 언급된 정보 자동 추출
           "프리랜서 개발자랑 3개월 용역계약, 월 500만원"
           → duration: 3개월, payment: 월 500만원 이미 수집됨

        3. 나머지 미수집 정보에 대해 질문 목록 생성
        """
        pass

    async def continue_interview(self, state: InterviewState, user_answer: str) -> InterviewState:
        """
        사용자 답변을 받아 인터뷰를 진행한다.

        - 답변에서 정보 추출 → state 업데이트
        - 다음 질문 결정
        - 모든 required 필드가 채워지면 optional로 넘어감
        - optional은 "기본값으로 할까요?" 형태로 질문
        - 사용자가 "그냥 기본으로 해줘"하면 나머지 전부 default 적용
        """
        pass

    async def check_completeness(self, state: InterviewState) -> dict:
        """
        수집된 정보가 계약서 생성에 충분한지 확인.

        Returns:
            {
                "ready": bool,
                "missing_required": ["field1", "field2"],
                "missing_optional": ["field3"],
                "warnings": ["IP 귀속이 명확하지 않으면 분쟁 가능"]
            }
        """
        pass

    # =============================================
    # Phase 2: 표준 서식 검색 (RAG)
    # =============================================

    async def find_template(self, state: InterviewState) -> Template:
        """
        RAG Agent를 통해 가장 적합한 표준 계약서 서식을 검색한다.

        검색 기준:
        1. 계약 유형 (service_contract, nda, etc.)
        2. 업종 (IT, 건설, 제조 등)
        3. 계약 규모 (소규모/대규모)

        반환: 표준 서식 텍스트 + 각 조항의 커스터마이징 포인트
        """
        pass

    # =============================================
    # Phase 3: 계약서 생성
    # =============================================

    async def generate_contract(self, state: InterviewState, template: Template) -> Contract:
        """
        수집된 정보 + 표준 서식을 기반으로 맞춤 계약서를 생성한다.

        생성 전략:
        1. 표준 서식의 각 조항을 하나씩 커스터마이징
           - 당사자명, 금액, 기간 등 변수 치환
           - 사용자 특수 조건 반영
           - 불필요한 조항 제거

        2. 누락된 중요 조항 자동 추가
           - 표준 서식에 없지만 사용자 상황에 필요한 조항
           - 예: IT 용역인데 소스코드 귀속 조항이 서식에 없으면 추가

        3. 조항 순서 및 번호 정리

        프롬프트 구조:
        System: "당신은 한국 법률 전문가입니다. 표준 계약서 서식을 기반으로
                사용자 상황에 맞는 계약서를 작성합니다."
        User: [수집된 정보] + [표준 서식] + [커스터마이징 지시]
        """
        pass

    # =============================================
    # Phase 4: 자체 검증 (Self-Review)
    # =============================================

    async def self_review(self, contract: Contract, state: InterviewState) -> ReviewedContract:
        """
        생성된 계약서를 Analyzer + Validator에게 넘겨 자동 검토한다.

        플로우:
        1. Analyzer가 생성된 계약서를 state.perspective 관점에서 분석
           - 사용자가 갑이면 → "갑에게 누락된 보호 조항 없나?"
           - 사용자가 을이면 → "을에게 불리한 조항 없나?"

        2. Validator가 법적 유효성 검증
           - 필수 조항 누락 여부
           - 법률 위반 조항 여부 (예: 근로기준법 위반 근로계약)

        3. 문제 발견 시 Drafter가 자동 수정
           - Analyzer/Validator의 피드백을 반영하여 조항 수정
           - 수정 후 다시 검증 (최대 2회)

        4. 최종 결과에 "자체 검증 완료" 표시
           - 어떤 검증을 거쳤는지 투명하게 공개
        """
        pass

    # =============================================
    # Phase 5: 최종 출력
    # =============================================

    async def export(self, contract: ReviewedContract, format: str = "docx") -> str:
        """
        최종 계약서를 DOCX 또는 PDF로 출력한다.

        포함 내용:
        1. 계약서 본문
        2. [부록] AI 분석 요약
           - 주요 조항 설명
           - 특별히 주의할 점
           - 자체 검증 결과
        """
        pass
```

### 8.3 인터뷰 대화 예시

```
시스템: 어떤 계약서가 필요하세요?

사용자: 프리랜서 개발자랑 3개월 용역계약 쓰려고 해. 월 500이야.

시스템: 용역계약서를 만들어드릴게요. 몇 가지만 더 확인할게요.
        말씀하신 내용 정리:
        ✅ 계약 유형: 용역계약
        ✅ 기간: 3개월
        ✅ 대금: 월 500만원

        📋 추가로 필요한 정보:
        1. 갑(발주자)의 회사명이나 이름은?
        2. 을(수급자)의 이름은?
        3. 구체적인 용역 내용은? (예: 웹앱 프론트엔드 개발)

사용자: 우리 회사는 주식회사 트리플에이치고, 프리랜서는 김개발이야.
        웹앱 백엔드 API 개발이야.

시스템: 감사합니다!
        ✅ 갑: 주식회사 트리플에이치
        ✅ 을: 김개발
        ✅ 업무: 웹앱 백엔드 API 개발

        📋 선택 사항 몇 가지가 있어요:

        1. 소스코드 귀속: 개발 결과물의 소유권을 누가 가질까요?
           → 기본값: 갑(트리플에이치)에게 귀속
           ⚠️ 이 부분이 명확하지 않으면 나중에 분쟁이 많이 생깁니다.

        2. 손해배상 한도: 어떻게 설정할까요?
           → 기본값: 계약금액(1,500만원) 한도 내 직접손해만

        3. 비밀유지: 양측 상호 비밀유지 의무를 넣을까요?
           → 기본값: 네

        기본값대로 진행할까요, 아니면 수정하고 싶은 부분이 있나요?

사용자: 기본으로 해줘. 근데 중도 해지할 때 위약금 조항도 넣어줘.

시스템: 알겠습니다. 중도 해지 위약금 조항을 추가할게요.
        위약금 금액은 어떻게 설정할까요?
        일반적으로 잔여 계약금액의 10~30% 수준입니다.

사용자: 20%로 해줘

시스템: 좋습니다. 모든 정보가 수집됐어요. 계약서를 생성할게요.

        [계약서 생성 중...]
        [자체 검증 중... ✅ Analyzer 검토 완료]
        [자체 검증 중... ✅ Validator 법적 유효성 확인]

        계약서가 완성됐습니다!

        📊 자체 검증 결과:
        - 전체 위험도: 2.1/10 (양호)
        - 검토된 조항: 15개
        - 발견된 문제: 0건
        - 참고: 을의 4대보험 미가입 사항은 용역계약 특성상
          정상이나, 실질적 근로 형태일 경우 근로계약으로
          재검토를 권장합니다.

        📎 [계약서 다운로드 (DOCX)]
```

---

## 9. Advisor Agent (법률 상담 에이전트) — NEW

### 9.1 Overview

```
모드 2(분석)와의 차이점:

분석 모드:  문서 전체를 체계적으로 스캔 → 리포트 생성
           (일괄 처리, 비동기, 몇 분 소요)

상담 모드:  특정 부분에 대해 대화형으로 깊이 파고듦
           (실시간, 대화 맥락 유지, 즉시 응답)


사용 시나리오:

1. "이 계약서 제8조가 좀 이상한데, 싸인해도 돼?"
   → 해당 조항만 집중 분석 + 위험도 판단 + 행동 제안

2. "갑이 일방적으로 해지할 수 있다는데, 이거 합법이야?"
   → 관련 법률 인용 + 유사 판례 + "이렇게 수정 요청하세요"

3. "경쟁사 이직 2년 금지라는데, 이거 무효 아니야?"
   → 경업금지 관련 판례 + 유효성 기준 설명 + 대응 전략

4. (이전 대화에 이어서) "그러면 제12조도 봐줘"
   → 같은 계약서 맥락 유지하면서 다른 조항 분석
```

### 9.2 상세 구현

```python
class AdvisorAgent:
    """
    대화형 법률 상담 에이전트.

    Analyzer와의 핵심 차이:
    1. 대화 히스토리를 유지한다 (multi-turn)
    2. 전체 문서가 아닌 특정 부분에 집중한다
    3. 분석보다 "판단 + 행동 제안"에 초점
    4. 사용자의 이해 수준에 맞춰 설명한다 (법률 비전문가 대상)
    """

    async def handle_message(
        self,
        message: str,
        session: AdvisorSession,
    ) -> AdvisorResponse:
        """
        사용자 메시지를 처리하고 응답한다.

        Args:
            message: 사용자 입력
            session: 대화 세션 (히스토리 + 문서 컨텍스트 포함)

        플로우:
        1. 의도 파악 (뭘 묻고 있는지)
        2. 문서에서 관련 부분 추출
        3. RAG로 법적 근거 검색
        4. 응답 생성 (판단 + 근거 + 행동 제안)
        5. 후속 질문 예상 & 제안
        """

        # ── 1. 의도 분류 ──
        intent = await self._classify_advisory_intent(message, session)
        # possible intents:
        #   "clause_risk_check"  → 특정 조항 위험도 확인
        #   "legality_question"  → 합법성 질문
        #   "action_advice"      → 어떻게 해야 하는지 조언
        #   "comparison"         → 표준과 비교
        #   "follow_up"          → 이전 대화 이어서

        # ── 2. 관련 조항 추출 ──
        relevant_clauses = await self._extract_relevant_clauses(
            message=message,
            document=session.document,
            history=session.history,
        )

        # ── 3. RAG 검색 (실시간) ──
        rag_result = await self.rag_agent.retrieve_for_advisory(
            question=message,
            clauses=relevant_clauses,
            # 상담 모드는 속도 우선 → 검색 범위 축소
            search_limit=5,
        )

        # ── 4. 응답 생성 ──
        response = await self._generate_advisory_response(
            intent=intent,
            message=message,
            clauses=relevant_clauses,
            rag_context=rag_result,
            history=session.history,
        )

        # ── 5. 세션 업데이트 ──
        session.history.append({"role": "user", "content": message})
        session.history.append({"role": "assistant", "content": response.text})

        return response

    async def _generate_advisory_response(
        self,
        intent: str,
        message: str,
        clauses: list,
        rag_context: RAGResult,
        history: list,
    ) -> AdvisorResponse:
        """
        상담 응답을 생성한다.

        응답 구조 (항상 이 형식):
        1. 판단 (한 줄 요약)
           "이 조항은 을에게 상당히 불리합니다."

        2. 이유 (구체적 설명)
           "~이유는 ... 때문입니다."

        3. 법적 근거 (RAG 기반)
           "민법 제393조에 따르면..."
           "유사 판례(2023다54321)에서..."

        4. 위험도 표시
           🔴 위험 / 🟡 주의 / 🟢 안전

        5. 행동 제안
           "상대방에게 다음과 같이 수정을 요청하세요: ..."
           또는 "이 조항은 업계 표준 수준이므로 수용해도 괜찮습니다."

        6. 후속 질문 제안 (최대 2개)
           "다른 조항도 확인해볼까요?"
           "수정 요청 문구를 만들어드릴까요?"

        톤 & 스타일:
        - 법률 비전문가도 이해할 수 있는 쉬운 말
        - 단정적이지 않게 ("~할 수 있습니다", "~의 가능성이 높습니다")
        - 반드시 "이 내용은 법률 자문이 아니며, 중요한 결정은 변호사와
          상담하세요"라는 면책 문구 포함
        """
        pass

    async def _extract_relevant_clauses(self, message, document, history):
        """
        사용자 메시지에서 어떤 조항을 묻고 있는지 파악.

        방법:
        1. 명시적 참조: "제8조", "8번 조항" → 직접 매칭
        2. 키워드 참조: "손해배상 부분" → 유사도 검색
        3. 대화 맥락: "그거" → history에서 이전에 논의한 조항 참조
        4. 전체 참조: "전체적으로 괜찮아?" → 전체 조항

        중요: follow_up일 경우 history에서 맥락을 가져온다
        "그러면 그 옆에 있는 조항은?" → 이전에 본 조항의 다음 조항
        """
        pass
```

### 9.3 대화 예시

```
사용자: [계약서 PDF 업로드]
        이거 내일 싸인하라는데, 좀 봐줘. 제8조가 좀 걸려.

Advisor: 제8조를 확인했습니다.

        제8조 (손해배상)
        "을은 본 계약 위반으로 인해 갑에게 발생한 일체의 손해를
         배상하여야 한다."

        🔴 위험 — 을에게 상당히 불리한 조항입니다.

        이유:
        "일체의 손해"라고 되어 있어서 배상 한도가 없습니다.
        이론적으로 계약금액의 몇 배를 넘는 금액도 배상해야 할 수
        있어요. 또한 직접 손해뿐 아니라 간접 손해, 기대이익 상실까지
        모두 포함될 수 있습니다.

        법적 근거:
        민법 제393조는 "통상의 손해"를 배상 원칙으로 하고 있어서,
        "일체의 손해"는 이보다 넓은 범위입니다.
        유사 판례(대법원 2019다238123)에서도 포괄적 손해배상
        조항의 범위를 제한적으로 해석한 바 있습니다.

        💡 행동 제안:
        상대방에게 이렇게 수정을 요청해보세요:
        "을은 본 계약 위반으로 인해 갑에게 발생한 직접 손해를
         배상하되, 그 총액은 본 계약의 총 계약금액을 초과하지
         아니한다."

        📌 다른 조항도 확인해볼까요?
        📌 수정 요청 이메일 초안을 만들어드릴까요?

        ※ 이 내용은 AI 기반 참고 정보이며, 법률 자문이 아닙니다.
          중요한 계약은 변호사와 상담하시는 것을 권장합니다.

────────────────────────────────

사용자: 제12조도 봐줘

Advisor: 제12조를 확인했습니다.

        제12조 (계약 해지)
        "갑은 30일 전 서면 통지로 본 계약을 해지할 수 있다."

        🟡 주의 — 해지권이 갑에게만 있습니다.

        이유:
        갑은 언제든 30일 전 통지만으로 해지할 수 있지만,
        을(당신)에게는 해지권이 부여되지 않았어요.
        또한 해지 시 정산 조건(이미 한 일에 대한 대금)이
        명시되어 있지 않습니다.

        ...

────────────────────────────────

사용자: 그러면 전체적으로 싸인해도 돼?

Advisor: 지금까지 확인한 내용을 종합하면:

        🔴 제8조 (손해배상) — 반드시 수정 필요
        🟡 제12조 (해지) — 수정 권장
        🟢 나머지 조항 — 업계 표준 수준

        제 판단으로는 지금 상태로 싸인하시는 것은 권장하지 않습니다.
        최소한 제8조의 손해배상 한도는 수정한 후 진행하시는 게 좋겠어요.

        💡 행동 제안:
        1. 상대방에게 제8조, 제12조 수정을 요청하세요
        2. 수정이 안 되면 → 최소한 제8조만이라도 협상
        3. 그래도 안 되면 → 변호사 상담 후 결정

        수정 요청 이메일을 만들어드릴까요?

        ※ 이 내용은 AI 기반 참고 정보이며, 법률 자문이 아닙니다.
```

### 9.4 Advisor Session 관리

```python
@dataclass
class AdvisorSession:
    """
    상담 세션. 대화 맥락을 유지한다.

    세션은 다음과 같은 경우 유지된다:
    - 같은 문서에 대해 연속 질문
    - "그거", "다른 조항도" 같은 참조 표현 사용

    세션은 다음과 같은 경우 초기화된다:
    - 새로운 문서 업로드
    - 사용자가 명시적으로 "새로 시작"
    - 30분 이상 비활동
    """
    id: str
    user_id: str

    # 문서 컨텍스트
    document: Document = None
    clauses: list = None

    # 대화 히스토리
    history: list = field(default_factory=list)  # [{role, content}]

    # 이전에 분석한 조항 (맥락 유지용)
    discussed_clauses: list = field(default_factory=list)

    # 세션 메타
    created_at: datetime = None
    last_active_at: datetime = None

    # 누적 분석 결과 (대화 중 쌓임)
    accumulated_findings: list = field(default_factory=list)
```

---

## 10. 업데이트된 Orchestrator (3모드 라우팅)

```python
class Orchestrator:
    """
    v2.0: 3가지 모드를 자동 분류하고 적절한 에이전트로 라우팅한다.
    """

    async def handle(self, request) -> Response:

        # ── 모드 분류 ──
        mode = await self._classify_mode(request)

        if mode == "draft":
            # 생성 모드: Drafter → Analyzer → Validator → 출력
            return await self._handle_draft(request)

        elif mode == "review":
            # 분석 모드: Analyzer + RAG → Validator → 리포트
            return await self._handle_review(request)

        elif mode == "advise":
            # 상담 모드: Advisor (대화형, 실시간)
            return await self._handle_advise(request)

    async def _classify_mode(self, request) -> str:
        """
        요청을 3가지 모드로 분류.

        분류 기준:

        Draft (생성):
        - 문서가 첨부되지 않음 + "만들어줘", "작성해줘", "계약서 필요"
        - "~계약 쓰려고 해", "서식 없는데"

        Review (분석):
        - 문서가 첨부됨 + "검토해줘", "분석해줘", "리뷰해줘"
        - "위험한 부분 찾아줘", "수정할 곳 알려줘"

        Advise (상담):
        - 문서가 첨부됨 + 특정 부분에 대한 질문
        - "제8조가 이상한데", "이거 싸인해도 돼?", "이 부분 괜찮아?"
        - 기존 세션이 있고 후속 질문인 경우
        - 감정/불안 표현: "좀 찝찝해", "걸리는데", "불안해"

        애매한 경우:
        - 문서 + "봐줘" → 짧은 질문이면 advise, 전체 검토 요청이면 review
        - LLM으로 최종 판단
        """
        pass

    async def _handle_draft(self, request) -> Response:
        """
        생성 모드 파이프라인:

        1. Drafter: 인터뷰 시작/진행
        2. (인터뷰 완료 후) Drafter: 표준 서식 검색 + 계약서 생성
        3. Analyzer: 생성된 계약서 자동 검토
        4. Validator: 법적 유효성 검증
        5. (문제 시) Drafter: 피드백 반영 수정
        6. 최종 계약서 출력 (DOCX/PDF)
        """
        pass

    async def _handle_review(self, request) -> Response:
        """
        분석 모드 파이프라인:
        (기존과 동일 — Section 4 참조)
        """
        pass

    async def _handle_advise(self, request) -> Response:
        """
        상담 모드 파이프라인:

        1. 세션 조회/생성
        2. Advisor Agent에게 메시지 전달
        3. 실시간 응답 반환
        4. 세션 업데이트
        """
        pass
```

---

## 11. 업데이트된 비용 예상

```
┌────────────────────────────────────────────────────┐
│               모드별 예상 비용                        │
│                                                     │
│  모드 1: 생성 (Draft)                               │
│  ─────────────────                                  │
│  인터뷰 (3-5 턴):      ~$0.01                      │
│  서식 검색 (RAG):       ~$0.002                     │
│  계약서 생성:           ~$0.03                      │
│  자체 검증 (Analyzer):  ~$0.05                      │
│  Validator:             ~$0.01                      │
│  Total:                 ~$0.10/건                   │
│                                                     │
│  모드 2: 분석 (Review)                              │
│  ─────────────────                                  │
│  (기존과 동일)                                       │
│  Total:                 ~$0.07/건                   │
│                                                     │
│  모드 3: 상담 (Advise)                              │
│  ─────────────────                                  │
│  메시지당 (RAG + 응답):  ~$0.008                    │
│  10턴 대화 기준:         ~$0.08/세션                │
│                                                     │
│  ─────────────────────                              │
│  참고: 변호사 계약서 작성 비용 50~200만원            │
│  참고: 변호사 계약서 검토 비용 30~100만원            │
│  참고: 변호사 상담 비용 10~30만원/시간               │
└────────────────────────────────────────────────────┘
```
