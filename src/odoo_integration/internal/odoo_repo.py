import enum
from typing import Optional, Annotated, Any

from fastapi import Depends

from src.config import Settings, get_settings
from src.data import (
    OdooEntity,
    OdooUser,
    OdooAddress,
    OdooProduct,
    OdooAttribute,
    OdooProductVariant,
    OdooDeliveryOption,
    OdooPickupLocation,
    OdooOrder,
    OdooBasketProduct,
    OdooCategory,
    OdooAttributeValue,
)
from src.infrastructure import RedisClient, get_redis_client


class RedisKeys(str, enum.Enum):
    USERS = "users"
    SYNC_ORDERCAST_USERS = "sync_ordercast_users"
    ADDRESSES = "addresses"
    PRODUCTS = "products"
    ATTRIBUTES = "attributes"
    ATTRIBUTE_VALUES = "attribute_values"
    CATEGORIES = "categories"
    PRODUCT_VARIANTS = "product_variants"
    DELIVERY_OPTIONS = "delivery_options"
    PICKUP_LOCATIONS = "pickup_locations"
    ORDERS = "orders"
    BASKET_PRODUCT = "basket_product"

    LAST_SUCCESSFUL_ORDERCAST_SYNC_DATE = "ordercast_sync_date"
    LAST_SUCCESSFUL_ODOO_SYNC_DATE = "odoo_sync_date"

    LAST_PRODUCT_SYNC = "last_product_sync"
    LAST_PRODUCT_VARIANT_SYNC = "last_pv_sync"

    DEFAULT_PRICE_RATE = "default_price_rate"


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
            RedisKeys.PRODUCTS: {
                "key": f"{self._prefix}:odoo:products",
                "model": OdooProduct,
            },
            RedisKeys.ATTRIBUTES: {
                "key": f"{self._prefix}:odoo:attributes",
                "model": OdooAttribute,
            },
            RedisKeys.ATTRIBUTE_VALUES: {
                "key": f"{self._prefix}:odoo:attribute_values",
                "model": OdooAttributeValue,
            },
            RedisKeys.CATEGORIES: {
                "key": f"{self._prefix}:odoo:categories",
                "model": OdooCategory,
            },
            RedisKeys.PRODUCT_VARIANTS: {
                "key": f"{self._prefix}:odoo:product_variants",
                "model": OdooProductVariant,
            },
            RedisKeys.DELIVERY_OPTIONS: {
                "key": f"{self._prefix}:odoo:delivery_options",
                "model": OdooDeliveryOption,
            },
            RedisKeys.PICKUP_LOCATIONS: {
                "key": f"{self._prefix}:odoo:pickup_locations",
                "model": OdooPickupLocation,
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
        entity_schema = self._schema[key]
        entity_key = entity_schema["key"]
        entity_model = entity_schema["model"]

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

    def set(self, key: RedisKeys, entity: OdooEntity) -> None:
        self._client.set(key=f"{self._prefix}:{key}", entity=entity.json())

    def remove(self, key: RedisKeys, entity_id: int) -> None:
        entity_schema = self._schema.get(key)
        entity_key = entity_schema.get("key")

        self._client.remove(f"{entity_key}:{entity_id}")

    def get_key(self, key: RedisKeys) -> Any:
        return self._client.get(f"{self._prefix}:{key}")

    def get_all(self, key: RedisKeys) -> list[int]:
        entity_schema = self._schema.get(key)
        entity_key = entity_schema.get("key")
        return list(self._client.sscan(entity_key))

    def get_len(self, key: RedisKeys) -> int:
        entity_schema = self._schema[key]
        entity_key = entity_schema["key"]
        return self._client.length(entity_key)

    def get_unique(
        self, compare_to: RedisKeys, comparable: RedisKeys, entities: list[Any]
    ) -> Any:
        entity_schema = self._schema[compare_to]
        compare_to_key = entity_schema["key"]
        return self._client.get_unique(
            compare_to=compare_to_key,
            comparable=f"{self._prefix}:{comparable}",
            entities=entities,
        )


def get_odoo_repo(
    redis_client: Annotated[RedisClient, Depends(get_redis_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OdooRepo:
    return OdooRepo(redis_client, settings.APP.SCHEMA_PREFIX)
