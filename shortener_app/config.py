from functools import lru_cache

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env")

    env_name: str = "Local"
    base_url: str = "http://localhost:8000"
    db_url: str = "sqlite+aiosqlite:///./shortener.db"
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_enabled: bool = True
    rate_limit_create: int = 10  # POST requests per minute
    rate_limit_read: int = 100   # GET requests per minute
    use_migrations: bool = False  # True for production, False for tests


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    print(f"Loading settings for: {settings.env_name}")
    return settings