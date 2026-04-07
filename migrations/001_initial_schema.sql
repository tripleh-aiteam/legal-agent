-- Legal Review Agent: 초기 DB 스키마
-- PostgreSQL + pgvector

-- pgvector 확장 활성화
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================
-- 1. 문서 테이블
-- ============================
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    file_name TEXT NOT NULL,
    file_type TEXT NOT NULL CHECK (file_type IN ('pdf', 'docx', 'hwp', 'hwpx')),
    file_size INT NOT NULL,
    storage_path TEXT NOT NULL,
    raw_text TEXT,
    clause_count INT DEFAULT 0,
    page_count INT DEFAULT 0,
    language TEXT DEFAULT 'ko',
    doc_type TEXT,
    parties JSONB DEFAULT '[]',
    security_scan_status TEXT DEFAULT 'pending'
        CHECK (security_scan_status IN ('pending', 'clean', 'suspicious', 'blocked')),
    security_scan_result JSONB DEFAULT '{}',
    status TEXT DEFAULT 'uploaded'
        CHECK (status IN ('uploaded', 'parsing', 'parsed', 'analyzing', 'completed', 'error')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================
-- 2. 조항 테이블
-- ============================
CREATE TABLE clauses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    clause_number TEXT,
    title TEXT,
    content TEXT NOT NULL,
    page_number INT,
    start_index INT,
    end_index INT,
    clause_type TEXT,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================
-- 3. 분석 결과 테이블
-- ============================
CREATE TABLE analysis_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    analysis_type TEXT NOT NULL
        CHECK (analysis_type IN ('risk_review', 'comparison', 'full_review')),
    llm_provider TEXT NOT NULL,
    llm_model TEXT NOT NULL,
    overall_risk_score FLOAT CHECK (overall_risk_score >= 0 AND overall_risk_score <= 10),
    risk_summary TEXT,
    input_tokens INT,
    output_tokens INT,
    estimated_cost FLOAT,
    processing_time_ms INT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================
-- 4. 위험 조항 결과 테이블
-- ============================
CREATE TABLE risk_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES analysis_results(id) ON DELETE CASCADE,
    clause_id UUID REFERENCES clauses(id),
    severity TEXT NOT NULL
        CHECK (severity IN ('critical', 'high', 'medium', 'low', 'info')),
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    original_text TEXT NOT NULL,
    suggested_text TEXT,
    suggestion_reason TEXT,
    related_law TEXT,
    precedent_ids UUID[] DEFAULT '{}',
    confidence_score FLOAT CHECK (confidence_score >= 0 AND confidence_score <= 1),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================
-- 5. RAG: 법령 조문 테이블
-- ============================
CREATE TABLE laws (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    law_id TEXT NOT NULL,
    law_name TEXT NOT NULL,
    article_number TEXT NOT NULL,
    article_title TEXT,
    content TEXT NOT NULL,
    enforcement_date DATE,
    last_amended_date DATE,
    category TEXT,
    embedding vector(1536),
    search_tokens tsvector GENERATED ALWAYS AS (
        to_tsvector('simple', law_name || ' ' || article_number || ' ' || content)
    ) STORED,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(law_id, article_number)
);

-- ============================
-- 6. RAG: 판례 테이블
-- ============================
CREATE TABLE precedents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_number TEXT NOT NULL UNIQUE,
    court TEXT NOT NULL,
    decision_date DATE,
    case_type TEXT,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    key_points TEXT,
    full_text TEXT,
    category TEXT,
    related_laws TEXT[] DEFAULT '{}',
    tags TEXT[] DEFAULT '{}',
    embedding vector(1536),
    search_tokens tsvector GENERATED ALWAYS AS (
        to_tsvector('simple', case_number || ' ' || title || ' ' || summary)
    ) STORED,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================
-- 7. RAG: 표준 계약서 조항 테이블
-- ============================
CREATE TABLE standard_clauses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_type TEXT NOT NULL,
    industry TEXT,
    clause_type TEXT NOT NULL,
    standard_text TEXT NOT NULL,
    is_mandatory BOOLEAN DEFAULT false,
    typical_range JSONB,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================
-- 8. 보안 감사 로그 테이블
-- ============================
CREATE TABLE security_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('critical', 'high', 'medium', 'low')),
    document_id UUID REFERENCES documents(id),
    user_id UUID,
    description TEXT NOT NULL,
    raw_payload JSONB DEFAULT '{}',
    action_taken TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================
-- 9. Draft 세션 테이블
-- ============================
CREATE TABLE draft_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_type TEXT NOT NULL,
    interview_data JSONB DEFAULT '{}',
    interview_complete BOOLEAN DEFAULT false,
    pending_fields JSONB DEFAULT '[]',
    generated_contract TEXT,
    review_result JSONB,
    status TEXT DEFAULT 'interviewing'
        CHECK (status IN ('interviewing', 'generating', 'reviewing', 'completed', 'error')),
    attempt INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================
-- 10. Advise 세션 테이블
-- ============================
CREATE TABLE advise_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id),
    conversation_history JSONB DEFAULT '[]',
    last_active_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================
-- 인덱스
-- ============================

-- 벡터 검색 인덱스 (IVFFlat)
CREATE INDEX idx_clauses_embedding ON clauses
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_laws_embedding ON laws
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_precedents_embedding ON precedents
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_standard_clauses_embedding ON standard_clauses
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);

-- 키워드 검색 인덱스 (GIN)
CREATE INDEX idx_laws_search ON laws USING gin (search_tokens);
CREATE INDEX idx_precedents_search ON precedents USING gin (search_tokens);

-- FK 인덱스
CREATE INDEX idx_clauses_document ON clauses(document_id);
CREATE INDEX idx_risk_findings_analysis ON risk_findings(analysis_id);
CREATE INDEX idx_analysis_document ON analysis_results(document_id);

-- ============================
-- Hybrid Search 함수
-- ============================

-- 법령 Hybrid Search (벡터 + 키워드 + RRF)
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
    article_title TEXT,
    content TEXT,
    vector_score FLOAT,
    text_score FLOAT,
    combined_score FLOAT
)
LANGUAGE sql
AS $$
    WITH vector_results AS (
        SELECT l.id, 1 - (l.embedding <=> query_embedding) AS score,
               ROW_NUMBER() OVER (ORDER BY l.embedding <=> query_embedding) AS rank
        FROM laws l
        ORDER BY l.embedding <=> query_embedding
        LIMIT match_count * 2
    ),
    text_results AS (
        SELECT l.id,
               ts_rank(l.search_tokens, plainto_tsquery('simple', query_text)) AS score,
               ROW_NUMBER() OVER (
                   ORDER BY ts_rank(l.search_tokens, plainto_tsquery('simple', query_text)) DESC
               ) AS rank
        FROM laws l
        WHERE l.search_tokens @@ plainto_tsquery('simple', query_text)
        LIMIT match_count * 2
    ),
    rrf AS (
        SELECT
            COALESCE(v.id, t.id) AS id,
            COALESCE(1.0 / (60 + v.rank), 0) * vector_weight AS v_score,
            COALESCE(1.0 / (60 + t.rank), 0) * text_weight AS t_score
        FROM vector_results v
        FULL OUTER JOIN text_results t ON v.id = t.id
    )
    SELECT
        l.id, l.law_name, l.article_number, l.article_title, l.content,
        r.v_score AS vector_score,
        r.t_score AS text_score,
        (r.v_score + r.t_score) AS combined_score
    FROM rrf r
    JOIN laws l ON r.id = l.id
    ORDER BY combined_score DESC
    LIMIT match_count;
$$;

-- 판례 Hybrid Search
CREATE OR REPLACE FUNCTION hybrid_search_precedents(
    query_embedding vector(1536),
    query_text TEXT,
    match_count INT DEFAULT 10,
    vector_weight FLOAT DEFAULT 0.7,
    text_weight FLOAT DEFAULT 0.3
)
RETURNS TABLE (
    id UUID,
    case_number TEXT,
    court TEXT,
    title TEXT,
    summary TEXT,
    key_points TEXT,
    combined_score FLOAT
)
LANGUAGE sql
AS $$
    WITH vector_results AS (
        SELECT p.id, 1 - (p.embedding <=> query_embedding) AS score,
               ROW_NUMBER() OVER (ORDER BY p.embedding <=> query_embedding) AS rank
        FROM precedents p
        ORDER BY p.embedding <=> query_embedding
        LIMIT match_count * 2
    ),
    text_results AS (
        SELECT p.id,
               ts_rank(p.search_tokens, plainto_tsquery('simple', query_text)) AS score,
               ROW_NUMBER() OVER (
                   ORDER BY ts_rank(p.search_tokens, plainto_tsquery('simple', query_text)) DESC
               ) AS rank
        FROM precedents p
        WHERE p.search_tokens @@ plainto_tsquery('simple', query_text)
        LIMIT match_count * 2
    ),
    rrf AS (
        SELECT
            COALESCE(v.id, t.id) AS id,
            COALESCE(1.0 / (60 + v.rank), 0) * vector_weight AS v_score,
            COALESCE(1.0 / (60 + t.rank), 0) * text_weight AS t_score
        FROM vector_results v
        FULL OUTER JOIN text_results t ON v.id = t.id
    )
    SELECT
        p.id, p.case_number, p.court, p.title, p.summary, p.key_points,
        (r.v_score + r.t_score) AS combined_score
    FROM rrf r
    JOIN precedents p ON r.id = p.id
    ORDER BY combined_score DESC
    LIMIT match_count;
$$;
