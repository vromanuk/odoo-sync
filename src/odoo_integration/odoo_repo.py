from typing import Optional, Annotated

import redis
from fastapi import Depends

from src.config import RedisConfig, get_settings, Settings
from .models import OdooUser, OdooEntity


class KeySchema:
    def __init__(self, prefix: str):
        self.prefix = prefix

    def odoo_users(self) -> str:
        return f"{self.prefix}:odoo:users"

    def odoo_user(self, odoo_user_id: int) -> str:
        return f"{self.prefix}:odoo:users:{odoo_user_id}"


class OdooRepo:
    def __init__(self, config: RedisConfig):
        self._config = config
        self._schema = KeySchema(config.PREFIX)
        self._client = redis.Redis(
            host=config.HOST, port=config.PORT, db=0, decode_responses=True
        )

    def _insert(
        self, entity: OdooEntity, entities_key: str, entity_key: str, pipeline=None
    ):
        is_single_insert = False
        if not pipeline:
            is_single_insert = True
            pipeline = self._client.pipeline()

        pipeline.set(entity_key, value=entity.json())
        pipeline.sadd(entities_key, entity.odoo_id)

        if is_single_insert:
            pipeline.execute()

    def _insert_many(self, entities: list[OdooEntity], key: str) -> None:
        pipeline = self._client.pipeline()
        for entity in entities:
            self._insert(
                entity=entity,
                entities_key=key,
                entity_key=f"{key}:{entity.odoo_id}",
                pipeline=pipeline,
            )
        pipeline.execute()

    def get_users(self) -> list[OdooUser]:
        user_ids = self._client.sscan_iter(self._schema.odoo_users())

        pipeline = self._client.pipeline()
        for user_id in user_ids:
            pipeline.get(self._schema.odoo_user(user_id))

        users_json = pipeline.execute()
        return [OdooUser.from_json(user_json) for user_json in users_json]

    def get_user(self, user_id: int) -> Optional[OdooUser]:
        user_json = self._client.get(self._schema.odoo_user(user_id))
        return OdooUser.from_json(user_json) if user_json else None

    def save_users(self, partners: list[OdooUser]) -> None:
        self._insert_many(partners, key=self._schema.odoo_users())

    def upsert_user(self, user_id, odoo_id):
        pass

    def save_user(self, user: OdooUser) -> None:
        self._insert(
            user, self._schema.odoo_users(), self._schema.odoo_user(user.odoo_id)
        )


# @lru_cache()
def get_odoo_repo(settings: Annotated[Settings, Depends(get_settings)]) -> OdooRepo:
    return OdooRepo(settings.REDIS)
