from typing import Optional, Annotated

from fastapi import Depends

from src.config import Settings, get_settings
from src.data.models import (
    OdooUser,
    OdooAddress,
    OdooProductGroup,
    OdooAttribute,
    OdooProduct,
)
from src.infrastructure import RedisClient, get_redis_client


class KeySchema:
    def __init__(self, prefix: str):
        self.prefix = prefix

    def odoo_users(self) -> str:
        return f"{self.prefix}:odoo:users"

    def odoo_user(self, user_id: int) -> str:
        return f"{self.odoo_users()}:{user_id}"

    def odoo_addresses(self) -> str:
        return f"{self.prefix}:odoo:addresses"

    def odoo_address(self, address_id: int) -> str:
        return f"{self.odoo_addresses()}:{address_id}"

    def odoo_product_groups(self) -> str:
        return f"{self.prefix}:odoo:product_groups"

    def odoo_product_group(self, product_group_id: int) -> str:
        return f"{self.odoo_product_groups()}:{product_group_id}"

    def odoo_attributes(self) -> str:
        return f"{self.prefix}:odoo:attributes"

    def odoo_attribute(self, attribute_id: int) -> str:
        return f"{self.odoo_attributes()}:{attribute_id}"

    def odoo_products(self) -> str:
        return f"{self.prefix}:odoo:products"

    def odoo_product(self, product_id: int) -> str:
        return f"{self.odoo_products()}:{product_id}"


class OdooRepo:
    def __init__(self, client: RedisClient, schema: KeySchema):
        self._client = client
        self._schema = schema

    def get_users(self) -> list[OdooUser]:
        return [
            OdooUser.from_json(user_json)
            for user_json in self._client.get_many(self._schema.odoo_users())
        ]

    def get_user(self, user_id: int) -> Optional[OdooUser]:
        user_json = self._client.get(self._schema.odoo_user(user_id))
        return OdooUser.from_json(user_json) if user_json else None

    def save_users(self, partners: list[OdooUser]) -> None:
        self._client.insert_many(partners, key=self._schema.odoo_users())

    def save_user(self, user: OdooUser) -> None:
        self._client.insert(
            user, self._schema.odoo_users(), self._schema.odoo_user(user.odoo_id)
        )

    def remove_user(self, user_id: int) -> None:
        self._client.remove(self._schema.odoo_user(user_id))

    def save_address(self, address: OdooAddress) -> None:
        self._client.insert(
            address,
            self._schema.odoo_addresses(),
            self._schema.odoo_address(address.odoo_id),
        )

    def get_address(self, address_id: int) -> Optional[OdooAddress]:
        address_json = self._client.get(self._schema.odoo_address(address_id))
        return OdooAddress.from_json(address_json) if address_json else None

    def remove_address(self, address_id: int):
        self._client.remove(self._schema.odoo_address(address_id))

    def get_product_group(self, product_group_id: int) -> Optional[OdooProductGroup]:
        product_group_json = self._client.get(
            self._schema.odoo_product_group(product_group_id)
        )
        return (
            OdooProductGroup.from_json(product_group_json)
            if product_group_json
            else None
        )

    def save_product_group(self, product_group: OdooProductGroup) -> None:
        self._client.insert(
            product_group,
            self._schema.odoo_addresses(),
            self._schema.odoo_address(product_group.odoo_id),
        )

    def get_attribute(self, attribute_id: int) -> Optional[OdooAttribute]:
        attribute_json = self._client.get(self._schema.odoo_attribute(attribute_id))
        return OdooAttribute.from_json(attribute_json) if attribute_json else None

    def save_attribute(self, attribute: OdooAttribute) -> None:
        self._client.insert(
            attribute,
            self._schema.odoo_addresses(),
            self._schema.odoo_address(attribute.odoo_id),
        )

    def get_product(self, product_id: int) -> Optional[OdooProduct]:
        product_json = self._client.get(self._schema.odoo_product(product_id))
        return OdooProduct.from_json(product_json) if product_json else None

    def save_product(self, product: OdooProduct) -> None:
        self._client.insert(
            product,
            self._schema.odoo_products(),
            self._schema.odoo_product(product.odoo_id),
        )


# @lru_cache()
def get_odoo_repo(
    redis_client: Annotated[RedisClient, Depends(get_redis_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OdooRepo:
    return OdooRepo(redis_client, KeySchema(settings.APP.SCHEMA_PREFIX))
