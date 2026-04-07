from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "GrandLine API"
    app_version: str = "0.1.0"
    debug: bool = False

    # PostgreSQL
    database_url: str = "postgresql+psycopg://grandline:grandline@localhost:5432/grandline"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_minutes: int = 10080  # 7 days

    # LLM Providers (Dial System)
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # Vivre Card (State Checkpointing)
    vivre_card_checkpoint_interval_seconds: int = 300  # 5 minutes
    vivre_card_cleanup_keep_last_n: int = 10

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = {"env_prefix": "GRANDLINE_", "env_file": ".env"}


settings = Settings()
