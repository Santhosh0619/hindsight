from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/hindsight"

    # Auth
    jwt_secret: str
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14

    # LLM — all optional, the app must fully function without any key
    llm_provider: str = "gemini"
    llm_api_key: str | None = None
    llm_model: str = "gemini-2.5-flash"
    groq_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"

    # Embeddings — no key needed, runs locally
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # App behaviour
    demo_mode: bool = True
    max_upload_bytes: int = 10_485_760
    retrieval_top_k: int = 20
    rrf_k: int = 60
    critic_threshold: float = 0.7
    max_correction_passes: int = 2
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key)


@lru_cache
def get_settings() -> Settings:
    # required fields (e.g. jwt_secret) are resolved from the environment at runtime by
    # pydantic-settings, which mypy can't see from the call site
    return Settings()  # type: ignore[call-arg]
