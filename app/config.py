from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/law_agent"
    database_url_async: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/law_agent"

    # LLM API Keys
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Embedding
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Security
    max_file_size_mb: int = 20
    rate_limit_per_minute: int = 10
    enable_pii_masking: bool = True

    # LLM Models
    analyzer_model: str = "claude-sonnet-4-20250514"
    validator_model: str = "gpt-4o-mini"
    classifier_model: str = "gpt-4o-mini"
    drafter_model: str = "claude-sonnet-4-20250514"
    advisor_model: str = "claude-sonnet-4-20250514"

    # OCR
    ocr_enabled: bool = True
    ocr_language: str = "kor+eng"

    # App
    app_env: str = "development"
    log_level: str = "INFO"

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


settings = Settings()
