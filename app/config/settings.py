import os
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseAppSettings(BaseSettings):
    BASE_DIR: Path = Path(__file__).parent.parent.parent
    DUCKDB_PATH: str = os.getenv("DUCKDB_PATH", str(BASE_DIR / "data" / "analytics.duckdb"))

    SECRET_KEY_ACCESS: str = os.getenv(
        "SECRET_KEY_ACCESS",
        "dev-secret-access-key-change-in-production-min-32-characters-long"
    )
    SECRET_KEY_REFRESH: str = os.getenv(
        "SECRET_KEY_REFRESH",
        "dev-secret-refresh-key-change-in-production-min-32-characters-long"
    )
    JWT_SIGNING_ALGORITHM: str = os.getenv("JWT_SIGNING_ALGORITHM", "HS256")

    @property
    def duckdb_path_absolute(self) -> Path:
        path = Path(self.DUCKDB_PATH)
        if path == Path(":memory:"):
            return path
        if not path.is_absolute():
            path = self.BASE_DIR / path
        return path


class Settings(BaseAppSettings):
    # PostgreSQL
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "events_user")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "events_pass")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "db")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "events_db")

    # Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))


    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
    )

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


class TestingSettings(BaseAppSettings):
    # PostgreSQL (for tests)
    POSTGRES_USER: str = "test_user"
    POSTGRES_PASSWORD: str = "test_password"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "test_db"

    # Redis (for tests)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 1

    SECRET_KEY_ACCESS: str = "test-secret-access-key-for-testing"
    SECRET_KEY_REFRESH: str = "test-secret-refresh-key-for-testing"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    def model_post_init(self, __context: dict[str, Any] | None = None) -> None:
        object.__setattr__(self, "DUCKDB_PATH", ":memory:")


def get_settings() -> BaseAppSettings:
    environment = os.getenv("ENVIRONMENT", "development")
    if environment == "testing":
        return TestingSettings()
    return Settings()


settings = get_settings()
