from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Annotated

import structlog
from fastapi import Depends

from src.data import OdooUser, OdooProduct, OdooAttribute, OdooCategory, CategoryType
from .internal.helpers import has_objects, get_i18n_field_as_dict
from .internal.odoo_manager import OdooManager, get_odoo_provider
from .internal.odoo_repo import OdooRepo, get_odoo_repo, RedisKeys
from .internal.ordercast_manager import OrdercastManager, get_ordercast_manager
from .internal.partner import validate_partners, create_partner_data
from .internal.validators import (
    validate_products,
    validate_categories,
    validate_product_variants,
    validate_attributes,
)

logger = structlog.getLogger(__name__)


class SyncManager:
    def __init__(
        self,
        repo: OdooRepo,
        odoo_manager: OdooManager,
        ordercast_manager: OrdercastManager,
    ) -> None:
        self.repo = repo
        self.odoo_manager = odoo_manager
        self.ordercast_manager = ordercast_manager

    def sync(self):
        logger.info("Start full syncing with Odoo.")
        self.sync_users()

        logger.info("Start receiving products from Odoo")
        self.sync_products(full_sync=True)

        logger.info("Start receiving order data from Odoo")
        self.sync_warehouses()

        logger.info("Start sync orders with Odoo")
        self.sync_orders_with_odoo(
            from_date=self.repo.get_key(RedisKeys.LAST_SUCCESSFUL_ORDERCAST_SYNC_DATE)
        )
        self.sync_orders_with_ordercast(
            from_date=self.repo.get_key(RedisKeys.LAST_SUCCESSFUL_ODOO_SYNC_DATE)
        )
        # self.check_deletion()?

    def sync_users(self):
        logger.info("Started syncing user's data with Ordercast.")
        self.sync_users_from_odoo()

    def sync_users_from_odoo(self):
        existing_odoo_users = self.repo.get_list(key=RedisKeys.USERS)
        partners = self.odoo_manager.receive_partner_users(
            exclude_user_ids=[p.odoo_id for p in existing_odoo_users]
        )
        validate_partners(
            partners=partners, ordercast_users=self.ordercast_manager.get_users()
        )

        logger.info(f"Received partners => {len(partners)}, started saving them.")

        users_to_sync = [
            create_partner_data(partner) for partner in partners if partner["email"]
        ]

        self.ordercast_manager.upsert_users(users_to_sync=users_to_sync)
        self.repo.insert_many(
            key=RedisKeys.USERS,
            entities=[
                OdooUser(
                    odoo_id=user["erp_id"],
                    sync_date=datetime.now(timezone.utc),
                    email=user["email"],
                )
                for user in users_to_sync
            ],
        )
        self.sync_billing(users=users_to_sync)

    def sync_billing(self, users: list[dict[str, Any]]) -> None:
        for partner in users:
            self.ordercast_manager.set_default_language(partner["language"])
            self.ordercast_manager.create_billing_address(partner)
            self.ordercast_manager.create_shipping_address(partner)

    def sync_products(self, full_sync: bool = False) -> None:
        categories = self.sync_categories_to_ordercast()
        attributes = self.sync_attributes_to_ordercast()
        products = self.sync_products_to_ordercast(full_sync=full_sync)
        self.sync_product_variants_to_ordercast(
            categories=categories,
            products=products,
            attributes=attributes,
            full_sync=full_sync,
        )

    def sync_categories_to_ordercast(self) -> dict[str, Any]:
        categories = self.odoo_manager.get_categories()
        logger.info(
            f"Received {len(categories['objects']) if categories['objects'] else 0} categories, start saving them."
        )
        if categories:
            validate_categories(categories)
            self.ordercast_manager.save_categories(categories["objects"])
            self.repo.insert_many(
                key=RedisKeys.CATEGORIES,
                entities=[
                    OdooCategory(
                        odoo_id=category["id"],
                        name=category["name"],
                        category_type=CategoryType.CLASS,
                        sync_date=datetime.now(timezone.utc),
                    )
                    for category in categories["objects"]
                ],
            )

        return categories

    def sync_attributes_to_ordercast(self) -> dict[str, Any]:
        attributes = self.odoo_manager.get_product_attributes()

        logger.info(
            f"Received {len(attributes['objects']) if attributes['objects'] else 0} attributes with total of {sum([len(a['values']) for a in attributes['objects'] if 'values' in a])} values, start saving them."
        )

        if attributes:
            validate_attributes(attributes)
            attributes_to_sync = [
                {
                    "id": value["id"],
                    "name": value["name"],
                    **({"position": value["position"]} if "position" in value else {}),
                    **get_i18n_field_as_dict(value, "name"),
                }
                for attribute in attributes["objects"]
                for value in attribute.get("values", [])
                if all(key in value for key in ("id", "name"))
            ]

            self.ordercast_manager.save_attributes(
                attributes_to_sync=attributes_to_sync
            )
            self.repo.insert_many(
                key=RedisKeys.ATTRIBUTES,
                entities=[
                    OdooAttribute(
                        odoo_id=attribute["id"],
                        name=attribute["name"],
                        sync_date=datetime.now(timezone.utc),
                    )
                    for attribute in attributes_to_sync
                ],
            )

        return attributes

    def sync_products_to_ordercast(self, full_sync: bool = False) -> dict[str, Any]:
        last_sync_date = (
            None if full_sync else self.repo.get_key(RedisKeys.LAST_PRODUCT_SYNC)
        )
        products = self.odoo_manager.get_products(last_sync_date)

        logger.info(f"Connected to Odoo")
        logger.info(
            f"Received {len(products['objects']) if has_objects(products) else 0} products, start saving them."
        )

        if has_objects(products):
            validate_products(products)

            products_to_sync = [
                {
                    "name": product["name"],
                    "is_removed": False,
                    "i18n_fields": get_i18n_field_as_dict(product, "name"),
                    "names": product["names"],
                    "category": product["categ_id"][0],
                }
                for product in products["objects"]
            ]

            self.ordercast_manager.save_products(products_to_sync)
            self.repo.insert_many(
                key=RedisKeys.PRODUCTS,
                entities=[
                    OdooProduct(odoo_id=product["erp_id"], name=product["name"])
                    for product in products_to_sync
                ],
            )
        return products

    def sync_product_variants_to_ordercast(
        self,
        categories: dict[str, Any],
        products: dict[str, Any],
        attributes: dict[str, Any],
        full_sync: bool = False,
    ) -> None:
        last_sync_date = (
            None
            if full_sync
            else self.repo.get_key(RedisKeys.LAST_PRODUCT_VARIANT_SYNC)
        )
        product_variants = self.odoo_manager.get_product_variants(last_sync_date)
        has_product_variants = has_objects(product_variants)

        logger.info(
            f"Received {len(product_variants['objects']) if has_product_variants else 0} products variants."
        )

        if has_product_variants:
            validate_product_variants(product_variants["objects"])
            logger.info(
                f"Starting saving products after saving categories and attributes."
            )
            self.ordercast_manager.save_product_variants(
                categories, products, attributes, product_variants
            )

    def sync_warehouses(self):
        delivery_options = self.odoo_manager.receive_delivery_options()
        logger.info(
            f"Received {len(delivery_options['objects']) if delivery_options and 'objects' in delivery_options else 0} delivery options, start saving them."
        )
        if delivery_options:
            self.ordercast_manager.save_delivery_option(
                delivery_options, odoo_repo=self.repo
            )

        warehouses = self.odoo_manager.receive_warehouses()
        logger.info(
            f"Received {len(warehouses['objects']) if warehouses and 'objects' in warehouses else 0} warehouses, start saving them."
        )
        if warehouses:
            self.ordercast_manager.save_warehouse(warehouses, odoo_repo=self.repo)

    def sync_orders_with_odoo(self, order_ids=None, from_date=None) -> None:
        orders = self.ordercast_manager.get_orders(
            order_ids, from_date=from_date, odoo_repo=self.repo
        )
        logger.info(f"Loaded {len(orders)} orders, start sending them to Odoo.")
        self.odoo_manager.sync_orders(orders)

    def sync_orders_with_ordercast(self, from_date=None) -> None:
        orders = self.odoo_manager.receive_orders(from_date=from_date)
        logger.info(
            f"Received {len(orders) if orders else 0} orders, start saving them."
        )
        if orders:
            self.ordercast_manager.sync_orders(orders, odoo_repo=self.repo)


@lru_cache()
def get_odoo_sync_manager(
    odoo_repo: Annotated[OdooRepo, Depends(get_odoo_repo)],
    odoo_provider: Annotated[OdooManager, Depends(get_odoo_provider)],
    ordercast_manager: Annotated[OrdercastManager, Depends(get_ordercast_manager)],
) -> SyncManager:
    return SyncManager(odoo_repo, odoo_provider, ordercast_manager)
