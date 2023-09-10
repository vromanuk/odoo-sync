import enum
from typing import Optional, Annotated

from fastapi import Depends

from src.config import Settings, get_settings
from src.data import (
    OdooEntity,
    OdooUser,
    OdooAddress,
    OdooProductGroup,
    OdooAttribute,
    OdooProduct,
)
from src.infrastructure import RedisClient, get_redis_client


class OdooKeys(str, enum.Enum):
    USERS = "users"
    ADDRESSES = "addresses"
    PRODUCT_GROUPS = "product_groups"
    ATTRIBUTES = "attributes"
    PRODUCTS = "products"


class OdooRepo:
    def __init__(self, client: RedisClient, prefix: str):
        self._client = client
        self._prefix = prefix

        self._schema = {
            OdooKeys.USERS: {"key": f"{self._prefix}:odoo:users", "model": OdooUser},
            OdooKeys.ADDRESSES: {
                "key": f"{self._prefix}:odoo:addresses",
                "model": OdooAddress,
            },
            OdooKeys.PRODUCT_GROUPS: {
                "key": f"{self._prefix}:odoo:product_groups",
                "model": OdooProductGroup,
            },
            OdooKeys.ATTRIBUTES: {
                "key": f"{self._prefix}:odoo:attributes",
                "model": OdooAttribute,
            },
            OdooKeys.PRODUCTS: {
                "key": f"{self._prefix}:odoo:products",
                "model": OdooProduct,
            },
        }

    def get_many(self, key: OdooKeys) -> list[OdooEntity]:
        entity_schema = self._schema.get(key)
        entity_key = entity_schema.get("key")
        entity_model = entity_schema.get("model")

        return [
            entity_model.from_json(entity_json)
            for entity_json in self._client.get_many(entity_key)
        ]

    def get(self, key: OdooKeys, entity_id: int) -> Optional[OdooEntity]:
        entity_schema = self._schema.get(key)
        entity_key = entity_schema.get("key")
        entity_model = entity_schema.get("model")

        entity_json = self._client.get(f"{entity_key}:{entity_id}")
        return entity_model.from_json(entity_json) if entity_json else None

    def insert_many(self, key: OdooKeys, entities: list[OdooEntity]) -> None:
        entity_schema = self._schema.get(key)
        entity_key = entity_schema.get("key")

        self._client.insert_many(entities, key=entity_key)

    def insert(self, key: OdooKeys, entity: OdooEntity) -> None:
        entity_schema = self._schema.get(key)
        entity_key = entity_schema.get("key")

        self._client.insert(
            entity=entity,
            entities_key=entity_key,
            entity_key=f"{entity_key}:{entity.odoo_id}",
        )

    def remove(self, key: OdooKeys, entity_id: int) -> None:
        entity_schema = self._schema.get(key)
        entity_key = entity_schema.get("key")

        self._client.remove(f"{entity_key}:{entity_id}")


# @lru_cache()
def get_odoo_repo(
    redis_client: Annotated[RedisClient, Depends(get_redis_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OdooRepo:
    return OdooRepo(redis_client, settings.APP.SCHEMA_PREFIX)
