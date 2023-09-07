from functools import lru_cache

from pydantic_settings import BaseSettings


class AppConfig(BaseSettings):
    PROJECT_NAME: str = "odoo-sync"
    API_PREFIX: str = "/api/v1"
    PORT: int = 8000
    HOST: str = "localhost"


class OdooConfig(BaseSettings):
    ODOO_HOST: str
    ODOO_DB: str
    ODOO_USER: str
    ODOO_PASSWORD: str
    ODOO_PORT: int
    ODOO_PROTOCOL: str
    ODOO_DISCOUNTS: str


class OrdercastConfig(BaseSettings):
    BASE_URL: str


class RedisConfig(BaseSettings):
    URL: str


class Settings(BaseSettings):
    APP: AppConfig
    ODOO: OdooConfig
    REDIS: RedisConfig
    ORDERCAST: OrdercastConfig


@lru_cache()
def get_settings() -> Settings:
    return Settings()
