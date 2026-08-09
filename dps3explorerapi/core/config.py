from typing import List, Union
from pydantic_settings import BaseSettings
from pydantic import AnyHttpUrl, Field, field_validator, AliasChoices


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

    PROJECT_NAME: str = "S3 Explorer"

    POSTGRES_DATABASE_URI: str
    BUCKET: str
    TRASH_BUCKET: str = "explorer-trash"
    AUDIT_BUCKET: str = "explorer-trash"
    AUDIT_HOT_DAYS: int = 30
    AUDIT_TOTAL_DAYS: int = 365

    DB_SCHEMA: str = "explorer"
    ENV: str = Field(default="dev", validation_alias=AliasChoices("ENV", "env"))

    CLIENTID: str     = Field(default="", validation_alias=AliasChoices("CLIENTID",     "clientId"))
    CLIENTSECRET: str = Field(default="", validation_alias=AliasChoices("CLIENTSECRET", "clientSecret"))
    TENANTID: str     = Field(default="", validation_alias=AliasChoices("TENANTID",     "tenantId"))
    USERID: str       = Field(default="", validation_alias=AliasChoices("USERID",       "userId"))

    DEV_AUTH_MODE: bool = True
    BOOTSTRAP_ADMIN_EMAIL: str = ""
    BOOTSTRAP_ADMIN_USERNAME: str = "admin"

    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    OTP_VALID_MINUTES: int = 10
    APPROVAL_VALID_MINUTES: int = 1440
    APPROVAL_BASE_URL: str = ""
    APPROVAL_FRONTEND_URL: str = ""

    DEACTIVATION_GRACE_DAYS: int = 30

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
