import os
from pydantic import field_validator
from pydantic_settings import BaseSettings
from pathlib import Path


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


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg://plinth:plinth_dev@localhost:5432/plinth_sip"
    ENV: str = "development"
    CONFIGS_DIR: str = _DEFAULT_CONFIGS
    ANTHROPIC_API_KEY: str = ""

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        return normalize_database_url(v) or v

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

# Ensure the key lands in os.environ so libraries that call
# os.environ.get("ANTHROPIC_API_KEY") directly (LangGraph, langchain-anthropic) find it.
if settings.ANTHROPIC_API_KEY and not os.environ.get("ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = settings.ANTHROPIC_API_KEY
