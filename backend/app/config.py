import logging

from pydantic import AliasChoices, Field, computed_field
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # Azure OpenAI
    azure_api_key: str = ""
    azure_endpoint: str = ""
    azure_api_version: str = "2024-12-01-preview"
    azure_model_name_mini: str = "gpt-5-mini"
    azure_deployment_mini: str = ""
    azure_model_name_full: str = "gpt-5.2"
    azure_deployment_full: str = ""

    # Auth
    jwt_secret: str = "change-me-in-production"  # noqa: S105
    allowed_emails_str: str = Field(
        default="",
        validation_alias=AliasChoices("allowed_emails", "ALLOWED_EMAILS"),
    )
    admin_emails_str: str = Field(
        default="",
        validation_alias=AliasChoices("admin_emails", "ADMIN_EMAILS"),
    )

    # Dataset source API keys (optional)
    datagov_api_key: str = ""
    kaggle_api_token: str = ""

    # Sandbox
    sandbox_timeout_seconds: int = 30
    sandbox_memory_limit_mb: int = 512

    # CORS
    cors_origins_str: str = Field(
        default="http://localhost:5173",
        validation_alias=AliasChoices("cors_origins", "CORS_ORIGINS"),
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def allowed_emails(self) -> list[str]:
        return [e.strip() for e in self.allowed_emails_str.split(",") if e.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def admin_emails(self) -> list[str]:
        return [e.strip().lower() for e in self.admin_emails_str.split(",") if e.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins_str.split(",") if o.strip()]

    model_config = {"env_file": "../.env", "env_file_encoding": "utf-8"}


settings = Settings()

# Startup security checks
if settings.jwt_secret == "change-me-in-production":  # noqa: S105
    logger.warning(
        "JWT_SECRET is using the default value. Set a strong, unique JWT_SECRET in production."
    )
