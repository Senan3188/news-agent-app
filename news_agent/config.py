"""Local application settings, optionally loaded from .env."""

from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, StringConstraints
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    ollama_model: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    ollama_base_url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    agent_timeout_seconds: float = Field(default=180, gt=0)
    agent_recursion_limit: int = Field(default=12, ge=2, le=100)
    database_url: SecretStr = Field(min_length=1)
    memory_recent_turns: int = Field(default=5, ge=1, le=10)
