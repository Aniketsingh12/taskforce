"""Application settings.

Loaded from environment variables (see .env.example at the repo root).
Everything has a sensible default so the MVP runs out of the box with no
external services — the demo falls back to the built-in `mock` model provider.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_name: str = "TaskForce"
    environment: str = "development"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # --- Persistence ---
    # SQLite file path. ":memory:" keeps everything in RAM (used by tests).
    db_path: str = "taskforce.db"

    # --- Scheduler ---
    scheduler_enabled: bool = True
    scheduler_tick_seconds: int = 30

    # --- Local models (Ollama) ---
    ollama_host: str = "http://localhost:11434"
    ollama_default_model: str = "llama3.1:8b"

    # --- Hosted gateway (OpenRouter) ---
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_default_model: str = "anthropic/claude-3.5-haiku"

    # --- Direct providers (optional) ---
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    groq_api_key: str | None = None

    # --- Fallback behaviour ---
    # If a local model call fails, fall back to this provider/model.
    fallback_provider: str = "mock"
    fallback_model: str = "mock-default"

    # --- Webhook security ---
    # Optional. When set, POST /api/webhooks/{id} must present this value in the
    # X-Webhook-Secret header. Unset (default) leaves webhooks open, which is
    # fine locally but should be set before exposing the API publicly.
    webhook_secret: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
