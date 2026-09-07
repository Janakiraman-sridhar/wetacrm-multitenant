from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "WeTa CRM"
    environment: str = "development"

    database_url: str = "sqlite:///./weta_crm_dev.db"
    jwt_secret: str = "dev-secret-change-in-production"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    cors_origins: str = "http://localhost:5173"
    # Public URL of the frontend app, used in emails (welcome, password reset).
    # Falls back to the first CORS origin when left blank.
    app_url: str = ""

    admin_email: str = "admin@wetacrm.com"
    admin_password: str = "admin123"

    # Platform Super Admin — the account that creates and manages tenants.
    # Distinct from a tenant's own "Super Admin" role.
    platform_admin_email: str = "superadmin@wetacrm.com"
    platform_admin_password: str = "superadmin123"

    # Name and slug of the tenant that existing single-tenant data is migrated into.
    default_tenant_name: str = "Default Workspace"
    default_tenant_slug: str = "default"

    # Run `alembic upgrade head` automatically on startup. Convenient in dev;
    # turn off in production if migrations are applied by the deploy pipeline.
    auto_migrate: bool = True
    #: How long a soft-deleted tenant is kept before the purge job removes it. The
    #: console tells an admin 30 days; changing this changes what that promise means.
    tenant_retention_days: int = 30

    redis_url: str = ""
    meili_url: str = ""
    meili_master_key: str = ""

    minio_endpoint: str = ""
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "weta-crm"
    minio_secure: bool = False
    upload_dir: str = "./uploads"

    # Platform key that wraps each tenant's data-encryption key. Required in
    # production; derived from JWT_SECRET in development so local dev needs no setup.
    pii_master_key: str = ""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "WeTa CRM <no-reply@weta.local>"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def public_app_url(self) -> str:
        """Base URL of the frontend for links in emails."""
        if self.app_url.strip():
            return self.app_url.strip().rstrip("/")
        origins = self.cors_origin_list
        return (origins[0] if origins else "http://localhost:5173").rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
