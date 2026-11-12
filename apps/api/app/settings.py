from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./legal.db"
    index_path: Path | None = None
    corpus_root: Path = Path("data/raw")
    app_env: Literal["development", "public"] = "public"
    admin_token: SecretStr = SecretStr("")
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    llm_provider: Literal["disabled", "groq", "organizer"] = "disabled"
    llm_model: str = ""
    groq_api_key: SecretStr = SecretStr("")
    organizer_api_key: SecretStr = SecretStr("")
    organizer_base_url: str = ""
    llm_timeout: float = Field(default=45, gt=0, le=120)
