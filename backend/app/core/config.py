from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"

    # Database (Supabase PostgreSQL). SQLite is supported for local tests only.
    database_url: str = "sqlite:///./leadpilot.db"

    # Supabase Auth
    supabase_url: str = ""
    supabase_jwt_secret: str = ""
    supabase_jwks_url: str = ""
    supabase_jwt_audience: str = "authenticated"

    cors_origins: str = "http://localhost:3000"

    # Research / crawling
    crawl_max_pages: int = 10
    fetch_timeout_seconds: float = 12.0
    fetch_max_bytes: int = 2_000_000
    fetch_max_redirects: int = 5
    domain_min_interval_seconds: float = 1.0
    respect_robots_txt: bool = True
    user_agent: str = "LeadPilotAI-Research/1.0 (+https://leadpilot.ai/bot)"
    social_content_limit: int = 8

    # YouTube Data API v3 (official API; the first permitted social integration)
    youtube_api_key: str = ""

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_timeout_seconds: float = 300.0
    ollama_num_ctx: int = 8192
    llm_max_attempts: int = 3
    llm_context_chars: int = 24_000
    llm_doc_chars: int = 4_000

    # Worker
    worker_concurrency: int = 2
    worker_poll_seconds: float = 2.0
    job_lease_seconds: int = 300
    job_max_attempts: int = 3

    # Imports
    import_max_bytes: int = 5 * 1024 * 1024
    import_max_rows: int = 1000

    # Rate limits (per user, per minute)
    rate_limit_research_per_min: int = 30
    rate_limit_import_per_min: int = 5

    pipeline_version: str = "1.0.0"
    prompt_version: str = "1.0"
    schema_version: str = "1.0"

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://") :]
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def jwks_url(self) -> str:
        if self.supabase_jwks_url:
            return self.supabase_jwks_url
        if self.supabase_url:
            return self.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
        return ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
