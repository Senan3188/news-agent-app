import pytest
from pydantic import ValidationError

from news_agent.config import Settings


@pytest.fixture(autouse=True)
def clear_ollama_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused/test")
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)


def test_ollama_settings_are_required():
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)
    assert {e["loc"][0] for e in error.value.errors()} == {"ollama_model", "ollama_base_url"}


def test_dotenv_values_and_environment_override(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("OLLAMA_MODEL=custom-model\nOLLAMA_BASE_URL=http://localhost:12345\n")
    settings = Settings(_env_file=env_file)
    assert settings.ollama_model == "custom-model"
    assert settings.ollama_base_url == "http://localhost:12345"
    monkeypatch.setenv("OLLAMA_MODEL", "environment-model")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:54321")
    settings = Settings(_env_file=env_file)
    assert settings.ollama_model == "environment-model"
    assert settings.ollama_base_url == "http://localhost:54321"


@pytest.mark.parametrize("name", ["OLLAMA_MODEL", "OLLAMA_BASE_URL"])
def test_blank_ollama_settings_are_rejected(name, monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv(name, "   ")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
