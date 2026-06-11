from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    external_service_url: str = "http://localhost:8001"
    external_service_timeout: float = 2.0
    jwt_secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 30
    cookie_secure: bool = True
