"""Configuration centrale — chargée depuis les variables d'environnement (.env)."""
from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Application
    APP_NAME: str = "Smart Transport AI"
    APP_ENV: str = "production"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # Sécurité / JWT
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Base de données
    POSTGRES_USER: str = "smarttransport"
    POSTGRES_PASSWORD: str = "smarttransport"
    POSTGRES_DB: str = "smarttransport"
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432

    # Redis (cache + jobs d'optimisation asynchrones)
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379

    # CORS — origines autorisées (frontend)
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "https://smart-transport.fr"]

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
