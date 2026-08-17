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
    # False only for local HTTP dev — a browser silently drops a Secure cookie sent
    # over plain http://, which would break the refresh flow entirely on localhost.
    # Must be true (the default) anywhere reachable over the network.
    cookie_secure: bool = True

    # LLM — all optional, the app must fully function without any key
    llm_provider: str = "gemini"
    llm_api_key: str | None = None
    # gemini-2.5-flash (the original default) is confirmed 404 for new accounts --
    # verified against a real key hitting Google's own generativelanguage API, whose
    # error body says exactly that. gemini-flash-latest resolves but returned a
    # persistent 503 "high demand" on this free-tier key across repeated attempts.
    # gemini-flash-lite-latest is the one that actually completed both a plain and a
    # structured call reliably in the same session -- verified with real calls, not
    # assumed from the model just being listed.
    llm_model: str = "gemini-flash-lite-latest"
    groq_api_key: str | None = None
    # Free-tier model IDs move fast (Phase 0's ADR) -- re-verify against the provider
    # before relying on these for a live call, same caution as `llm_model` above.
    # llama-3.3-70b-versatile (the original default) was confirmed retired by querying
    # https://api.groq.com/openai/v1/models directly with a real key -- Groq's current
    # lineup has no Llama chat models at all. gpt-oss-20b is the current fast/free-tier
    # general-purpose model with tool-calling and structured-output support, which this
    # project's structured() calls need.
    groq_model: str = "openai/gpt-oss-20b"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    # Embeddings — no key needed, runs locally
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # App behaviour
    demo_mode: bool = True
    max_upload_bytes: int = 10_485_760
    # A worker that claims a job and crashes before completing/failing it leaves the
    # job stuck `running` -- another worker reclaims it once its lease is this old.
    job_lease_seconds: int = 120
    retrieval_top_k: int = 20
    rrf_k: int = 60
    critic_threshold: float = 0.7
    max_correction_passes: int = 2
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    # Phase 14 hardening — see docs/modules/phase-14-hardening/NFR.md "Constraints".
    # Must stay comfortably above max_upload_bytes (a legitimate postmortem's raw_text
    # can be right up against that 10MB field cap, plus JSON structure overhead) --
    # this is an outer defense-in-depth boundary, not meant to be tighter than the
    # field-level cap it wraps.
    max_request_bytes: int = 15_728_640
    llm_request_timeout_seconds: int = 30

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
