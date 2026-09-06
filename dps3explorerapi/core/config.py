from typing import List
from pydantic_settings import BaseSettings
from pydantic import AnyHttpUrl, Field, field_validator, AliasChoices


class Settings(BaseSettings):
    API_V1_STR: str = "/api/v2/explorer"
    SERVER_NAME: str = ""
    BACKEND_CORS_ORIGINS: str = ""

    PROJECT_NAME: str = "S3 Explorer"

    POSTGRES_DATABASE_URI: str
    BUCKET: str
    TRASH_BUCKET: str = "s3explorer"
    AUDIT_BUCKET: str = "s3explorer"
    AUDIT_HOT_DAYS: int = 30
    AUDIT_TOTAL_DAYS: int = 365

    # Primary S3 switch (same boto3 API):
    #   empty → real AWS | set → MinIO/LocalStack (host: localhost:9000, compose: minio:9000)
    S3_ENDPOINT_URL: str = ""
    AWS_DEFAULT_REGION: str = "us-east-1"
    # Optional. AWS mode: set keys or omit for IAM.
    # Local MinIO: leave empty → get_s3_client uses minioadmin defaults.
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""

    DB_SCHEMA: str = "explorer"
    ENV: str = Field(default="dev", validation_alias=AliasChoices("ENV", "env"))

    CLIENTID: str     = Field(default="", validation_alias=AliasChoices("CLIENTID",     "clientId"))
    CLIENTSECRET: str = Field(default="", validation_alias=AliasChoices("CLIENTSECRET", "clientSecret"))
    TENANTID: str     = Field(default="", validation_alias=AliasChoices("TENANTID",     "tenantId"))
    USERID: str       = Field(default="", validation_alias=AliasChoices("USERID",       "userId"))

    BOOTSTRAP_ADMIN_EMAIL: str = ""
    BOOTSTRAP_ADMIN_USERNAME: str = "admin"

    # Google OAuth / JWT session
    GOOGLE_CLIENT_ID: str = ""
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    COOKIE_SECURE: bool = False  # True in production (HTTPS)
    COOKIE_SAMESITE: str = "lax"
    CSRF_HEADER_NAME: str = "X-CSRF-Token"

    SMTP_HOST: str = ""
    # Accept SMTP_PORT or legacy PORT (some .env files still use PORT=587).
    SMTP_PORT: int = Field(default=587, validation_alias=AliasChoices("SMTP_PORT", "PORT"))
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    OTP_VALID_MINUTES: int = 10
    APPROVAL_VALID_MINUTES: int = 1440
    APPROVAL_BASE_URL: str = ""
    APPROVAL_FRONTEND_URL: str = ""

    DEACTIVATION_GRACE_DAYS: int = 30

    model_config = {"env_file": "../.env", "extra": "ignore"}


settings = Settings()
