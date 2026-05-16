"""Application configuration via environment variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # API
    debug: bool = False
    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # LLM
    llm_provider: str = "mock"  # "anthropic" | "mock"
    anthropic_api_key: str | None = None
    llm_model: str = "claude-opus-4-7"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.2  # low temp for regulatory consistency

    # Drafting
    max_concurrent_sections: int = 5
    section_draft_timeout_s: int = 120


settings = Settings()
