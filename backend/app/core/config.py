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

    # Outbound email - see services/email_service.py for the two transports
    # (HTTP mail relay vs direct SMTP) this powers. Same scheme as the
    # sibling sunlease-expms project's cpanel-mail-relay.php setup.
    SMTP_HOST: str = os.environ.get("HRMS_SMTP_HOST", "")
    SMTP_PORT: int = int(os.environ.get("HRMS_SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.environ.get("HRMS_SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.environ.get("HRMS_SMTP_PASSWORD", "")
    SMTP_USE_SSL: bool = os.environ.get("HRMS_SMTP_USE_SSL", "false").lower() == "true"
    SMTP_FROM_EMAIL: str = os.environ.get("HRMS_SMTP_FROM_EMAIL", "")
    SMTP_FROM_NAME: str = os.environ.get("HRMS_SMTP_FROM_NAME", "HRMS — Employee Data Management")

    # HTTP mail relay (scripts/cpanel-mail-relay.php) - used INSTEAD of
    # direct SMTP whenever set. Needed on platforms that block outbound
    # SMTP ports; the relay script is uploaded to the same cPanel server
    # as the mailbox and called over HTTPS instead.
    MAIL_RELAY_URL: str = os.environ.get("HRMS_MAIL_RELAY_URL", "")
    MAIL_RELAY_SECRET: str = os.environ.get("HRMS_MAIL_RELAY_SECRET", "")

    class Config:
        env_prefix = "HRMS_"


settings = Settings()

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
