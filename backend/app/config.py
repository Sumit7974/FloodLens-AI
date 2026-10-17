"""Application configuration using Pydantic Settings."""
from functools import lru_cache
from typing import List, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    # Application
    app_name: str = "FloodLens AI Backend"
    environment: str = Field(default="development", description="development, testing, staging, production")
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    api_v1_prefix: str = "/api/v1"
    ws_v1_prefix: str = "/ws/v1"

    # Database (PostgreSQL + PostGIS)
    database_url: str = Field(
        default="postgresql+psycopg2://floodlens:floodlens_secure_password@localhost:5432/floodlens_db",
        description="Database connection URL. Defaults to local PostgreSQL.",
    )
    test_database_url: str = "sqlite:///./test_floodlens.db"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30

    # Security & Auth
    jwt_secret: str = Field(
        default="dev-insecure-jwt-secret-replace-in-production-123456",
        description="Secret key for signing JWT tokens. Must be changed in production.",
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # CORS Origins (accepts comma-separated string or list)
    cors_origins: Union[List[str], str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8081",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    # Operational Mode: historical_demo, test, live_observation, model_estimate
    operational_mode: str = "historical_demo"

    # Geospatial & Storage
    data_dir: str = "./data"
    raster_storage_path: str = "./data/rasters"
    reports_storage_path: str = "./data/reports"

    # Logging
    log_level: str = "INFO"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_testing(self) -> bool:
        return self.environment == "testing"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
