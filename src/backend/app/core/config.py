from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "GrandLine API"
    app_version: str = "0.1.0"
    debug: bool = False

    # PostgreSQL
    database_url: str = "postgresql+psycopg://grandline:grandline@localhost:5432/grandline"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = {"env_prefix": "GRANDLINE_", "env_file": ".env"}


settings = Settings()
