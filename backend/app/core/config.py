import os
from typing import ClassVar
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "HRMS — Employee Data Management"
    SECRET_KEY: str = os.environ.get("HRMS_SECRET_KEY", "dev-secret-change-in-production-please")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12
    DATABASE_URL: str = os.environ.get("HRMS_DATABASE_URL", "sqlite:///../data/hrms.db")

    UPLOAD_DIR: str = os.environ.get("HRMS_UPLOAD_DIR", "../data/hrms-attachments")

    _cors_origins = os.environ.get("HRMS_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    CORS_ORIGINS: ClassVar[list] = [origin.strip() for origin in _cors_origins.split(",")]

    class Config:
        env_prefix = "HRMS_"


settings = Settings()

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
