from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from src.config import OrdercastConfig, Settings, get_settings


class OrdercastApi:
    def __init__(self, config: OrdercastConfig):
        self._config = config

    def get_user_by_email(self, email: str):
        return f"{email}hello@gmail.com"

    def save_users(self, users):
        pass

    def get_partner_by_email(self, email):
        pass

    def upsert_user(self, email, defaults):
        pass

    def create_user_profile(self, user_id, defaults):
        pass


# @lru_cache()
def get_ordercast_api(
    settings: Annotated[Settings, Depends(get_settings)]
) -> OrdercastApi:
    return OrdercastApi(settings.ORDERCAST)
