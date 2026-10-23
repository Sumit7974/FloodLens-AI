"""Application configuration using Pydantic Settings."""
from functools import lru_cache
from typing import List, Optional, Union
from pydantic import Field, field_validator, model_validator
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
    floodlens_repo_root: Optional[str] = None
    data_dir: str = "./data"
    raster_storage_path: str = "./data/rasters"
    reports_storage_path: str = "./data/reports"
    satellite_output_dir: Optional[str] = None

    # Logging
    log_level: str = "INFO"

    # Demo Participant Allowlist (authenticated user IDs only; email authorization is forbidden)
    demo_participant_ids: Union[List[str], str] = Field(
        default_factory=lambda: [
            "usr_citizen_demo",
            "user_demo_participant_01",
            "user_test_participant_01",
            "demo_participant_field_01",
        ],
        description="Allowlist of authenticated user IDs authorized for demo simulation alerts",
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        """Normalize cloud hosted postgres connection URLs (Render, Neon, Supabase, Heroku)."""
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("postgres://"):
                v = "postgresql+psycopg2://" + v[len("postgres://"):]
            elif v.startswith("postgresql://") and not v.startswith("postgresql+"):
                v = "postgresql+psycopg2://" + v[len("postgresql://"):]
        return v

    @field_validator("cors_origins", "demo_participant_ids", mode="before")
    @classmethod
    def assemble_string_or_list(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    @model_validator(mode="after")
    def validate_production_credentials(self) -> "Settings":
        """Require strong, non-default credentials outside local development."""
        if self.environment not in ("development", "testing"):
            insecure_markers = [
                "dev-insecure-jwt-secret-replace-in-production-123456",
                "replace-with-a-secure-random-secret-key-at-least-32-characters",
                "changeme",
            ]
            if (
                any(marker == self.jwt_secret for marker in insecure_markers)
                or "insecure" in self.jwt_secret.lower()
                or len(self.jwt_secret) < 32
            ):
                raise ValueError(
                    f"Insecure or default JWT_SECRET detected for environment '{self.environment}'. "
                    "Non-local environments require a strong, randomly generated JWT secret of at least 32 characters."
                )
            if "floodlens_secure_password" in self.database_url:
                raise ValueError(
                    f"Default database credentials detected for environment '{self.environment}'. "
                    "Non-local environments require secure, explicitly provisioned database credentials."
                )
        return self


    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_testing(self) -> bool:
        return self.environment == "testing"

    @property
    def masked_database_url(self) -> str:
        """Return database URL with password credentials safely masked."""
        try:
            from sqlalchemy.engine.url import make_url
            return make_url(self.database_url).render_as_string(hide_password=True)
        except Exception:
            from urllib.parse import urlsplit, urlunsplit
            try:
                parsed = urlsplit(self.database_url)
                if parsed.password:
                    user = parsed.username or ""
                    host = parsed.hostname or ""
                    port = f":{parsed.port}" if parsed.port else ""
                    netloc = f"{user}:***@{host}{port}"
                    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
                return self.database_url
            except Exception:
                return "masked_database_url"



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
