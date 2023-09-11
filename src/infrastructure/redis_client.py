from typing import Annotated

import redis
from fastapi import Depends

from src.config import RedisConfig, Settings, get_settings
from src.data import OdooEntity


class RedisClient:
    def __init__(self, config: RedisConfig):
        self._config = config
        self._client = redis.Redis(
            host=config.HOST, port=config.PORT, db=0, decode_responses=True
        )

    def get(self, key: str):
        return self._client.get(key)

    def get_many(self, key: str) -> list:
        entity_ids = self._client.sscan_iter(key)

        pipeline = self._client.pipeline()
        for entity in entity_ids:
            pipeline.get(f"{key}:{entity}")

        return pipeline.execute()

    def insert(self, entity, entities_key: str, entity_key: str, pipeline=None):
        is_single_insert = False
        if not pipeline:
            is_single_insert = True
            pipeline = self._client.pipeline()

        pipeline.set(entity_key, value=entity.json())
        pipeline.sadd(entities_key, entity.odoo_id)

        if is_single_insert:
            pipeline.execute()

    def insert_many(self, entities: list[OdooEntity], key: str) -> None:
        pipeline = self._client.pipeline()
        for entity in entities:
            self.insert(
                entity=entity,
                entities_key=key,
                entity_key=f"{key}:{entity.odoo_id}",
                pipeline=pipeline,
            )
        pipeline.execute()

    def remove(self, key: str) -> None:
        self._client.unlink(key)

    def ping(self):
        return self._client.ping()

    def length(self, key: str):
        return self._client.scard(key)


# @lru_cache()
def get_redis_client(
    settings: Annotated[Settings, Depends(get_settings)]
) -> RedisClient:
    return RedisClient(settings.REDIS)
