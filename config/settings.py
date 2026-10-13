"""Central configuration: everything comes from environment variables (or .env)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)

_PLACEHOLDER_PREFIXES = ("dummy", "your_", "changeme", "xxx")


def is_real_key(value: str | None) -> bool:
    """True when a key looks like a real credential and not a placeholder."""
    if not value:
        return False
    return not value.strip().lower().startswith(_PLACEHOLDER_PREFIXES)


def _str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    secret_key: str
    jwt_algorithm: str
    access_token_minutes: int
    database_url: str
    llm_provider: str
    llm_api_key: str
    llm_base_url: str
    ollama_base_url: str
    llm_model_primary: str
    llm_model_fallback: str
    llm_max_tokens: int
    llm_timeout: float
    google_places_api_key: str
    yelp_api_key: str
    spoonacular_api_key: str
    reddit_client_id: str
    reddit_client_secret: str
    reddit_user_agent: str
    rate_limit_per_min: int
    auth_rate_limit_per_min: int
    cache_ttl_seconds: int
    session_ttl_minutes: int
    peak_mode: bool
    log_level: str
    otel_service_name: str
    otel_console: bool
    otel_endpoint: str

    @property
    def llm_enabled(self) -> bool:
        if self.llm_provider == "ollama":
            return True
        if self.llm_provider == "openai_compatible":
            return is_real_key(self.llm_api_key) and bool(self.llm_base_url)
        return False

    @property
    def effective_cache_ttl(self) -> int:
        """Caches live 3x longer in peak mode to absorb traffic spikes."""
        return self.cache_ttl_seconds * (3 if self.peak_mode else 1)


def load_settings() -> Settings:
    return Settings(
        app_name="Voice Food Ordering Chatbot",
        app_env=_str("APP_ENV", "development"),
        secret_key=_str("SECRET_KEY", "dev-secret-change-me-this-is-at-least-32-bytes"),
        jwt_algorithm="HS256",
        access_token_minutes=_int("ACCESS_TOKEN_MINUTES", 720),
        database_url=_str("DATABASE_URL", "sqlite:///./local.db"),
        llm_provider=_str("LLM_PROVIDER", "none").lower(),
        llm_api_key=_str("LLM_API_KEY"),
        llm_base_url=_str("LLM_BASE_URL").rstrip("/"),
        ollama_base_url=_str("OLLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/"),
        llm_model_primary=_str("LLM_MODEL_PRIMARY", "Qwen/Qwen2.5-7B-Instruct"),
        llm_model_fallback=_str("LLM_MODEL_FALLBACK", "mistralai/Mistral-7B-Instruct-v0.3"),
        llm_max_tokens=_int("LLM_MAX_TOKENS", 120),
        llm_timeout=_float("LLM_TIMEOUT_SECONDS", 12.0),
        google_places_api_key=_str("GOOGLE_PLACES_API_KEY"),
        yelp_api_key=_str("YELP_API_KEY"),
        spoonacular_api_key=_str("SPOONACULAR_API_KEY"),
        reddit_client_id=_str("REDDIT_CLIENT_ID"),
        reddit_client_secret=_str("REDDIT_CLIENT_SECRET"),
        reddit_user_agent=_str("REDDIT_USER_AGENT", "voice-food-bot/1.0"),
        rate_limit_per_min=_int("RATE_LIMIT_PER_MIN", 40),
        auth_rate_limit_per_min=_int("AUTH_RATE_LIMIT_PER_MIN", 30),
        cache_ttl_seconds=_int("CACHE_TTL_SECONDS", 300),
        session_ttl_minutes=_int("SESSION_TTL_MINUTES", 60),
        peak_mode=_bool("PEAK_MODE", False),
        log_level=_str("LOG_LEVEL", "INFO").upper(),
        otel_service_name=_str("OTEL_SERVICE_NAME", "voice-food-ordering-chatbot"),
        otel_console=_bool("OTEL_CONSOLE", False),
        otel_endpoint=_str("OTEL_EXPORTER_OTLP_ENDPOINT"),
    )


settings = load_settings()
