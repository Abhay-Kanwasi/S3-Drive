from typing import List, Union
from pydantic_settings import BaseSettings
from pydantic import AnyHttpUrl, field_validator
from dotenv import load_dotenv
import os

load_dotenv()
config_env = os.environ


class Settings(BaseSettings):
    API_V1_STR: str = "/api/v2/explorer"
    SERVER_NAME: str = ""
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    MONGO_DATABASE: str = ""
    MONGO_DATABASE_URI: str = ""
    PROJECT_NAME: str = "S3 Explorer"
    POSTGRES_DATABASE_URI: str = config_env["POSTGRES_DATABASE_URI"]
    BUCKET: str = config_env["BUCKET"]
    ENV: str = config_env["env"]

    CLIENTID: str = config_env["clientId"]
    CLIENTSECRET: str = config_env["clientSecret"]
    TENANTID: str = config_env["tenantId"]
    USERID: str = config_env["userId"]

    JWT_SECRET_KEY: str = config_env.get("JWT_SECRET_KEY", "change-me-in-production")
    JWT_ALGORITHM: str = config_env.get("JWT_ALGORITHM", "HS256")
    DB_SCHEMA: str = config_env.get("DB_SCHEMA", "datapoem")
    TRASH_BUCKET: str = config_env.get("TRASH_BUCKET", "explorer-trash")

    # Audit config — override if lifecycle policy or bucket changes
    AUDIT_BUCKET: str = config_env.get("AUDIT_BUCKET", config_env.get("TRASH_BUCKET", "explorer-trash"))
    AUDIT_HOT_DAYS: int = int(config_env.get("AUDIT_HOT_DAYS", "30"))
    AUDIT_TOTAL_DAYS: int = int(config_env.get("AUDIT_TOTAL_DAYS", "365"))

    # SMTP (OTP emails) — set in .env
    SMTP_HOST: str = config_env.get("SMTP_HOST", "")
    SMTP_PORT: int = int(config_env.get("PORT", config_env.get("SMTP_PORT", "587")))
    SMTP_USERNAME: str = config_env.get("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = config_env.get("SMTP_PASSWORD", "")
    SMTP_FROM: str = config_env.get("SMTP_FROM", config_env.get("SMTP_USERNAME", ""))
    OTP_VALID_MINUTES: int = int(config_env.get("OTP_VALID_MINUTES", "10"))
    APPROVAL_VALID_MINUTES: int = int(config_env.get("APPROVAL_VALID_MINUTES", "1440"))
    # Public API base for approve/reject links in email (no trailing slash)
    APPROVAL_BASE_URL: str = config_env.get("APPROVAL_BASE_URL", "")
    # Public frontend base used for the authenticated approval review page (e.g. https://app.example.com).
    # When set, email approve/reject links point here at /admin/approval; the SPA reads id/token/action,
    # GETs review JSON, then POSTs JSON with the signed-in approver's Bearer token.
    APPROVAL_FRONTEND_URL: str = config_env.get("APPROVAL_FRONTEND_URL", "")

    # Days after S3 deactivation before group memberships are purged by the cron job,
    # and the window within which reactivation is allowed.
    DEACTIVATION_GRACE_DAYS: int = int(config_env.get("DEACTIVATION_GRACE_DAYS", "30"))


settings = Settings()
