from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    APP_ENV: str = "development"
    DEBUG: bool = False
    PROJECT_NAME: str = "iCare API"
    API_V1_STR: str = "/api/v1"

    # Security
    SECRET_KEY: str = "change-this-in-production"

    # Database
    DATABASE_URL: str = "postgresql://username:password@localhost:5432/iCare"

    # CORS
    ALLOWED_ORIGINS: list[str] = ["*"]

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Logging
    LOG_LEVEL: str = "INFO"


settings = Settings()
