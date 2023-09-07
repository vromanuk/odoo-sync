from functools import lru_cache
from typing import Optional

import aioredis
from fastapi import Depends

from src.config import RedisConfig, get_settings
from .models import OdooUser


class OdooRepo:
    def __init__(self, config: RedisConfig):
        self._config = config
        self._client = aioredis.from_url(config.URL)

    async def _insert(self, entity, entities_key: str, entity_key: str):
        # TODO: think of introducing pipeline somewhere above
        await self._client.hset(entity_key, mapping=entity.to_dict())
        await self._client.sadd(entities_key, entity.id)

    async def _insert_many(self, entities, entities_key: str, entity_key: str) -> None:
        for entity in entities:
            await self._insert(entity, entities_key, entity_key)

    async def get_users(self) -> list[OdooUser]:
        # TODO: test and replace strings with key_schema
        user_ids = await self._client.sscan_iter("odoo_users")
        pipeline = self._client.pipeline()
        for user_id in user_ids:
            pipeline.hgetall(f"odoo_user:{user_id}")

        users = pipeline.execute()
        return [OdooUser(**user) for user in users]

    async def get_user(self, user_id: int) -> Optional[OdooUser]:
        user = await self._client.hgetall(f"odoo_user:{user_id}")
        return (
            OdooUser(**{key.decode(): value.decode() for key, value in user.items()})
            if user
            else None
        )

    async def save_users(self, partners) -> None:
        await self._insert_many(
            partners, entities_key="odoo_users", entity_key="odoo_user"
        )


@lru_cache()
def get_odoo_repo(settings: Depends(get_settings)) -> OdooRepo:
    return OdooRepo(settings.REDIS)
