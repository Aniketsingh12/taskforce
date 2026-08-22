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

    # --- Together AI (open-source models via API) ---
    together_api_key: str | None = None
    together_base_url: str = "https://api.together.ai/v1"
    # A well-established, high-capability general-purpose default. Together's
    # catalog moves fast — /api/models queries it live (see api/models.py) so
    # the Models page and picker always show the ACTUAL current lineup with
    # pricing; this default is only the pre-filled fallback before that loads.
    together_default_model: str = "meta-llama/Llama-3.3-70B-Instruct-Turbo"

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

    # --- Public-demo access control ---
    # The deployed app is meant to be shareable: anyone with the link can browse
    # and run workflows live. What they can't do is spend money or change data.
    #
    # ADMIN_TOKEN unset (the default) disables ALL gating below — local dev and
    # the test suite behave exactly as they did before. Set it in production.
    admin_token: str | None = None
    # Anonymous visitors are forced onto this provider so a public demo can
    # never bill you. The mock provider streams realistic role-aware output and
    # even simulates tool calls, so the demo still shows the whole platform.
    demo_provider: str = "mock"
    demo_model: str = "mock-default"

    # --- Spend circuit breaker ---
    # Hard ceiling on cumulative run cost per UTC day, across every trigger
    # source. Runs are refused once it's hit. None = no limit.
    # This is the only control that bounds your maximum bill — a rate limit
    # caps velocity, not total.
    daily_cost_limit_usd: float | None = 1.0

    # --- Rate limiting (per client IP, run-triggering endpoints only) ---
    rate_limit_runs: int = 20
    rate_limit_window_seconds: int = 3600

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
