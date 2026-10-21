from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional, List
import os


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    app_name: str = "Personal AI Agent"
    app_version: str = "0.1.0"
    debug: bool = False
    host: str = "127.0.0.1"
    port: int = 8000

    database_url: str = "sqlite+aiosqlite:///./data/agent.db"
    log_level: str = "INFO"
    log_file: str = "./logs/agent.log"

    # Model Provider Configuration
    model_provider: str = "gemini"
    
    # Nemotron / OpenAI-compatible settings
    model_base_url: str = ""
    model_api_key: str = ""
    model_name: str = "nvidia/nemotron-3-ultra"
    model_timeout: int = 120
    model_max_tokens: int = 8192
    model_temperature: float = 0.1

    # Gemini settings
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    gemini_timeout: int = 60
    gemini_max_retries: int = 3

    browser_headless: bool = True
    browser_timeout: int = 30000
    browser_user_data_dir: str = "./data/browser_profile"

    allowed_directories: List[str] = Field(default_factory=lambda: ["./data/workspace"])
    max_file_size_mb: int = 50
    max_task_duration_seconds: int = 3600
    max_tool_calls_per_task: int = 100
    max_retries: int = 3

    approval_required_for_level2: bool = True
    approval_required_for_level3: bool = True
    approval_timeout_seconds: int = 300

    scheduler_enabled: bool = False
    scheduler_check_interval_seconds: int = 60

    memory_enabled: bool = True
    memory_max_items: int = 1000

    telemetry_enabled: bool = False


settings = Settings()


def get_allowed_directories() -> List[str]:
    dirs = []
    for d in settings.allowed_directories:
        abs_path = os.path.abspath(d)
        if os.path.exists(abs_path) or abs_path.startswith(os.path.abspath("./data")):
            dirs.append(abs_path)
    return dirs