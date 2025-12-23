from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    app_name: str = "ForgeBreaker"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://localhost:5432/forgebreaker"

    mlforge_url: str = "https://backend-production-b2b8.up.railway.app"

    anthropic_api_key: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
