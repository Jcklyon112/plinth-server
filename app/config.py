import os
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from urllib.parse import urlparse


# Resolve configs: bundled in repo (Render), sibling folder (plinth-sip monorepo), or /configs in Docker.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_BUNDLED = _BACKEND_DIR / "configs"
_MONOREPO = _BACKEND_DIR.parent / "configs"
if _BUNDLED.is_dir():
    _DEFAULT_CONFIGS = str(_BUNDLED)
elif _MONOREPO.is_dir():
    _DEFAULT_CONFIGS = str(_MONOREPO)
else:
    _DEFAULT_CONFIGS = "/configs"


def normalize_database_url(url: str | None) -> str | None:
    """Render and other hosts often provide postgresql://; we use psycopg v3."""
    if not url:
        return url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and "+psycopg" not in url.split("://", 1)[0]:
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def _running_on_render() -> bool:
    return os.environ.get("RENDER") == "true"


def _load_dotenv() -> bool:
    """Local dev only — never load .env on Render/production hosts."""
    if _running_on_render():
        return False
    return os.environ.get("ENV", "development").lower() != "production"


_ENV_FILE = _BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _load_dotenv() and _ENV_FILE.is_file() else None,
        extra="ignore",
    )

    DATABASE_URL: str
    ENV: str = "development"
    CONFIGS_DIR: str = _DEFAULT_CONFIGS
    ANTHROPIC_API_KEY: str = ""

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        return normalize_database_url(v) or v


settings = Settings()


def database_host(url: str) -> str | None:
    return urlparse(url).hostname


def validate_production_database() -> None:
    """Fail fast when deployed without a linked Postgres DATABASE_URL."""
    host = database_host(settings.DATABASE_URL)
    on_cloud = _running_on_render() or settings.ENV.lower() == "production"
    if not on_cloud:
        return
    if host in (None, "localhost", "127.0.0.1"):
        raise RuntimeError(
            "DATABASE_URL is missing or still points at localhost. "
            "On Render: create a PostgreSQL instance, open your web service → "
            "Environment → Link Database, then redeploy so DATABASE_URL is injected."
        )

# Ensure the key lands in os.environ so libraries that call
# os.environ.get("ANTHROPIC_API_KEY") directly (LangGraph, langchain-anthropic) find it.
if settings.ANTHROPIC_API_KEY and not os.environ.get("ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = settings.ANTHROPIC_API_KEY
