from src.config import OrdercastConfig


class OrdercastApi:
    def __init__(self, config: OrdercastConfig):
        self._config = config

    async def get_user_by_email(self, email: str):
        return f"{email}hello@gmail.com"

    async def save_users(self, users):
        pass
