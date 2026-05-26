import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ENV_FILE = _BACKEND_DIR / ".env"


def _running_on_render() -> bool:
    return os.environ.get("RENDER") == "true"


def _load_dotenv() -> bool:
    if _running_on_render():
        return False
    return os.environ.get("ENV", "development").lower() != "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _load_dotenv() and _ENV_FILE.is_file() else None,
        extra="ignore",
    )

    ENV: str = "development"
    X_RAPIDAPI_KEY: str = Field(default="", validation_alias="X-RAPIDAPI-KEY")
    CORS_ORIGINS: str = ""


settings = Settings()

if settings.X_RAPIDAPI_KEY and not os.environ.get("X-RAPIDAPI-KEY"):
    os.environ["X-RAPIDAPI-KEY"] = settings.X_RAPIDAPI_KEY
if settings.CORS_ORIGINS and not os.environ.get("CORS_ORIGINS"):
    os.environ["CORS_ORIGINS"] = settings.CORS_ORIGINS


def parse_cors_origins(
    env_value: str | None = None,
    *,
    defaults: list[str] | None = None,
) -> list[str]:
    raw = (env_value if env_value is not None else settings.CORS_ORIGINS or "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return list(defaults or [])
