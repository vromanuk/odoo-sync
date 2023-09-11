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
    OdooDeliveryOption,
    OdooWarehouse,
    OdooOrder,
    OdooBasketProduct,
)
from src.infrastructure import RedisClient, get_redis_client


class RedisKeys(str, enum.Enum):
    USERS = "users"
    ADDRESSES = "addresses"
    PRODUCT_GROUPS = "product_groups"
    ATTRIBUTES = "attributes"
    PRODUCTS = "products"
    DELIVERY_OPTIONS = "delivery_options"
    WAREHOUSES = "warehouses"
    ORDERS = "orders"
    BASKET_PRODUCT = "basket_product"

    LAST_SUCCESSFUL_ORDERCAST_SYNC_DATE = "ordercast_sync_date"
    LAST_SUCCESSFUL_ODOO_SYNC_DATE = "odoo_sync_date"


class OdooRepo:
    def __init__(self, client: RedisClient, prefix: str):
        self._client = client
        self._prefix = prefix

        self._schema = {
            RedisKeys.USERS: {"key": f"{self._prefix}:odoo:users", "model": OdooUser},
            RedisKeys.ADDRESSES: {
                "key": f"{self._prefix}:odoo:addresses",
                "model": OdooAddress,
            },
            RedisKeys.PRODUCT_GROUPS: {
                "key": f"{self._prefix}:odoo:product_groups",
                "model": OdooProductGroup,
            },
            RedisKeys.ATTRIBUTES: {
                "key": f"{self._prefix}:odoo:attributes",
                "model": OdooAttribute,
            },
            RedisKeys.PRODUCTS: {
                "key": f"{self._prefix}:odoo:products",
                "model": OdooProduct,
            },
            RedisKeys.DELIVERY_OPTIONS: {
                "key": f"{self._prefix}:odoo:delivery_options",
                "model": OdooDeliveryOption,
            },
            RedisKeys.WAREHOUSES: {
                "key": f"{self._prefix}:odoo:warehouses",
                "model": OdooWarehouse,
            },
            RedisKeys.ORDERS: {
                "key": f"{self._prefix}:odoo:orders",
                "model": OdooOrder,
            },
            RedisKeys.BASKET_PRODUCT: {
                "key": f"{self._prefix}:odoo:basket_product",
                "model": OdooBasketProduct,
            },
        }

    def get_list(self, key: RedisKeys) -> list[OdooEntity]:
        entity_schema = self._schema.get(key)
        entity_key = entity_schema.get("key")
        entity_model = entity_schema.get("model")

        return [
            entity_model.from_json(entity_json)
            for entity_json in self._client.get_many(entity_key)
        ]

    def get(self, key: RedisKeys, entity_id: int) -> Optional[OdooEntity]:
        entity_schema = self._schema.get(key)
        entity_key = entity_schema.get("key")
        entity_model = entity_schema.get("model")

        entity_json = self._client.get(f"{entity_key}:{entity_id}")
        return entity_model.from_json(entity_json) if entity_json else None

    def insert_many(self, key: RedisKeys, entities: list[OdooEntity]) -> None:
        entity_schema = self._schema.get(key)
        entity_key = entity_schema.get("key")

        self._client.insert_many(entities, key=entity_key)

    def insert(self, key: RedisKeys, entity: OdooEntity) -> None:
        entity_schema = self._schema.get(key)
        entity_key = entity_schema.get("key")

        self._client.insert(
            entity=entity,
            entities_key=entity_key,
            entity_key=f"{entity_key}:{entity.odoo_id}",
        )

    def remove(self, key: RedisKeys, entity_id: int) -> None:
        entity_schema = self._schema.get(key)
        entity_key = entity_schema.get("key")

        self._client.remove(f"{entity_key}:{entity_id}")

    def get_key(self, key: RedisKeys):
        return self._client.get(f"{self._prefix}:{key}")

    def get_len(self, key: RedisKeys):
        return self._client.length(f"{self._prefix}:{key}")


# @lru_cache()
def get_odoo_repo(
    redis_client: Annotated[RedisClient, Depends(get_redis_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OdooRepo:
    return OdooRepo(redis_client, settings.APP.SCHEMA_PREFIX)
