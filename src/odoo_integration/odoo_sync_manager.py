from datetime import datetime
from typing import Any, Annotated, Optional

import structlog
from fastapi import Depends

from src.commons import set_context_value, get_ctx
from .internal.odoo_manager import OdooManager, get_odoo_provider
from .internal.odoo_repo import OdooRepo, get_odoo_repo, RedisKeys
from .internal.ordercast_manager import OrdercastManager, get_ordercast_manager
from .internal.utils import (
    has_objects,
    set_ordercast_id,
    set_user_ordercast_id,
    validate_partners,
)
from .internal.utils.builders import (
    get_partner_data,
    get_attribute_data,
    get_product_data,
    get_product_variant_data,
    get_delivery_option_data,
    get_pickup_location_data,
)
from .internal.utils.helpers import set_attribute_value_ordercast_id
from .internal.validators import (
    validate_products,
    validate_categories,
    validate_product_variants,
    validate_attributes,
    validate_delivery_options,
    validate_pickup_locations,
)
from .internal.webhook_handler import WebhookHandler

logger = structlog.getLogger(__name__)


class OdooSyncManager:
    def __init__(
        self,
        repo: OdooRepo,
        odoo_manager: OdooManager,
        ordercast_manager: OrdercastManager,
        webhook_handler: WebhookHandler,
    ) -> None:
        self.repo = repo
        self.odoo_manager = odoo_manager
        self.ordercast_manager = ordercast_manager
        self.webhook_handler = webhook_handler

    def handle_webhook(self, topic: str, **kwargs: dict[str, Any]) -> None:
        self.webhook_handler.handle(topic=topic, **kwargs)

    def sync(self) -> None:
        logger.info("Load common data")
        self.load_commons()

        logger.info("Start full syncing with Odoo.")
        self.sync_users()

        logger.info("Start receiving products from Odoo")
        self.sync_products(full_sync=True)

        logger.info(
            "Start receiving order data from Odoo => "
            "delivery methods & pickup locations"
        )
        self.sync_delivery_methods_and_pickup_locations()

        logger.info("Start sync orders with Odoo")
        self.sync_orders_with_odoo(
            from_date=self.repo.get_key(RedisKeys.LAST_SUCCESSFUL_ORDERCAST_SYNC_DATE)
        )
        logger.info("Start syncing orders with Ordercast")
        self.sync_orders_with_ordercast(
            from_date=self.repo.get_key(RedisKeys.LAST_SUCCESSFUL_ODOO_SYNC_DATE)
        )
        # self.check_deletion()?

    def sync_users(self) -> None:
        logger.info("Started syncing user's data with Ordercast")
        self.sync_users_from_odoo_to_ordercast()
        self.sync_users_from_ordercast_to_odoo()

    def sync_users_from_odoo_to_ordercast(self) -> None:
        existing_odoo_users = self.repo.get_list(key=RedisKeys.USERS)
        partners = self.odoo_manager.receive_partner_users(
            exclude_user_ids=[p.odoo_id for p in existing_odoo_users]  # type: ignore
        )
        validate_partners(
            partners=partners, ordercast_users=self.ordercast_manager.get_users()
        )

        logger.info(f"Received partners => {len(partners)}, started saving them.")

        users_to_sync = [
            get_partner_data(partner) for partner in partners if partner["email"]
        ]
        self.ordercast_manager.upsert_users(users_to_sync=users_to_sync)

        users_with_ordercast_id = set_user_ordercast_id(
            users_to_sync, source=self.ordercast_manager.get_users
        )
        self.odoo_manager.save_users(users_to_sync=users_with_ordercast_id)
        self.sync_billing(users_to_sync=users_with_ordercast_id)

    def sync_users_from_ordercast_to_odoo(self) -> None:
        users_to_sync = self.ordercast_manager.get_users_with_related_entities()
        logger.info(
            f"Received merchants => {len(users_to_sync)}, started syncing with Odoo."
        )
        self.odoo_manager.sync_users(users_to_sync)

    def sync_billing(self, users_to_sync: list[dict[str, Any]]) -> None:
        for partner in users_to_sync:
            self.ordercast_manager.create_billing_address(partner)
            self.ordercast_manager.create_shipping_address(partner)

    def sync_products(self, full_sync: bool = False) -> None:
        self.sync_categories_to_ordercast()
        self.sync_attributes_to_ordercast()
        self.sync_products_to_ordercast(full_sync=full_sync)
        self.sync_product_variants_to_ordercast(
            full_sync=full_sync,
        )

    def sync_categories_to_ordercast(self) -> None:
        categories = self.odoo_manager.get_categories()
        logger.info(
            f"""
            Received {len(categories['objects']) if categories['objects'] else 0} 
            categories, start saving them.
            """
        )
        if categories:
            validate_categories(categories)
            self.ordercast_manager.save_categories(
                categories_to_sync=categories["objects"]
            )
            self.odoo_manager.save_categories(
                categories_to_sync=set_ordercast_id(
                    items=categories["objects"],
                    source=self.ordercast_manager.get_categories,
                )
            )

    def sync_attributes_to_ordercast(self) -> None:
        attributes = self.odoo_manager.get_product_attributes()

        logger.info(
            f"""
            Received {len(attributes['objects']) if attributes['objects'] else 0} 
            attributes with total of 
            {sum([len(a['values']) for a in attributes['objects'] if 'values' in a])} 
            values, start saving them.
            """
        )

        if attributes:
            validate_attributes(attributes)
            attributes_to_sync = [
                get_attribute_data(attribute) for attribute in attributes["objects"]
            ]
            attribute_values_to_sync = {
                a["id"]: a.get("values", []) for a in attributes["objects"]
            }

            logger.info("Syncing attributes")
            self.ordercast_manager.save_attributes(
                attributes_to_sync=attributes_to_sync
            )
            attributes_with_ordercast_id = set_ordercast_id(
                items=attributes_to_sync,
                source=self.ordercast_manager.get_attributes,
            )
            self.odoo_manager.save_attributes(
                attributes_to_sync=attributes_with_ordercast_id
            )

            self.sync_attribute_values(
                attribute_values_to_sync=attribute_values_to_sync,
                attributes_with_ordercast_id=attributes_with_ordercast_id,
            )

    def sync_attribute_values(
        self,
        attribute_values_to_sync: dict[int, Any],
        attributes_with_ordercast_id: list[dict[str, Any]],
    ) -> None:
        logger.info("Syncing attribute values")

        attributes_odoo_to_ordercast_mapper = {
            a["id"]: a["ordercast_id"] for a in attributes_with_ordercast_id
        }

        self.ordercast_manager.save_attribute_values(
            attributes_odoo_to_ordercast_mapper=attributes_odoo_to_ordercast_mapper,
            attribute_values_to_sync=attribute_values_to_sync,
        )
        self.odoo_manager.save_attribute_values(
            attribute_values_to_sync=set_attribute_value_ordercast_id(
                attributes_odoo_to_ordercast_mapper=attributes_odoo_to_ordercast_mapper,
                attribute_values=[
                    value
                    for attribute_value in attribute_values_to_sync.values()
                    for value in attribute_value
                ],
                source=self.ordercast_manager.get_attribute_values,
            )
        )

    def sync_products_to_ordercast(self, full_sync: bool = False) -> None:
        last_sync_date = (
            None if full_sync else self.repo.get_key(RedisKeys.LAST_PRODUCT_SYNC)
        )
        products = self.odoo_manager.get_products(last_sync_date)

        logger.info(
            f"""Received {len(products['objects']) if has_objects(products) else 0}
            products, start saving them.
            """
        )

        if has_objects(products):
            validate_products(products)

            products_to_sync = [
                get_product_data(product, odoo_repo=self.repo)
                for product in products["objects"]
            ]

            self.ordercast_manager.save_products(products_to_sync=products_to_sync)
            self.odoo_manager.save_products(
                products_to_sync=set_ordercast_id(
                    items=products_to_sync,
                    source=self.ordercast_manager.get_products,
                    key="sku",
                )
            )

    def sync_product_variants_to_ordercast(
        self,
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
            f"""
            Received {len(product_variants['objects']) if has_product_variants else 0}
            products variants.
            """
        )

        if has_product_variants:
            validate_product_variants(product_variants["objects"])
            logger.info(
                """
                Starting saving product variants after
                saving categories and attributes.
                """
            )

            product_variants_to_sync = [
                get_product_variant_data(
                    product_variant=product_variant, odoo_repo=self.repo
                )
                for product_variant in product_variants["objects"]
            ]

            units = self.odoo_manager.get_units()
            self.ordercast_manager.save_product_variants(
                product_variants=product_variants_to_sync,
                units=units,
            )
            self.odoo_manager.save_product_variants(
                product_variants_to_sync=set_ordercast_id(
                    items=product_variants_to_sync,
                    source=self.ordercast_manager.get_product_variants,
                    key="slug_name",
                )
            )

    def sync_delivery_methods_and_pickup_locations(self) -> None:
        delivery_options = self.odoo_manager.receive_delivery_options()
        logger.info(
            f"""
Received {len(delivery_options['objects']) if has_objects(delivery_options) else 0} 
delivery options, start saving them."""
        )
        if delivery_options:
            validate_delivery_options(delivery_options)

            delivery_options_to_sync = [
                get_delivery_option_data(delivery_option)
                for delivery_option in delivery_options["objects"]
            ]

            self.ordercast_manager.save_delivery_options(delivery_options_to_sync)
            self.odoo_manager.save_delivery_options(delivery_options_to_sync)

        pickup_locations = self.odoo_manager.receive_pickup_locations(
            odoo_repo=self.repo
        )
        logger.info(
            f"""
Received {len(pickup_locations['objects']) if has_objects(pickup_locations) else 0}
warehouses, start saving them."""
        )
        if pickup_locations:
            validate_pickup_locations(pickup_locations)

            pickup_locations_to_sync = [
                get_pickup_location_data(pickup_location)
                for pickup_location in pickup_locations["objects"]
            ]

            self.ordercast_manager.save_pickup_locations(
                pickup_locations_to_sync=pickup_locations_to_sync
            )
            self.odoo_manager.save_pickup_locations(
                pickup_locations_to_sync=pickup_locations_to_sync
            )

    def sync_orders_with_odoo(
        self,
        order_ids: Optional[list[int]] = None,
        from_date: Optional[datetime] = None,
    ) -> None:
        orders = self.ordercast_manager.get_orders_for_sync(
            odoo_repo=self.repo, order_ids=order_ids, from_date=from_date
        )
        logger.info(f"Loaded {len(orders)} orders, start sending them to Odoo.")
        _, unique_orders = self.repo.get_diff(
            compare_to=RedisKeys.ORDERS,
            comparable=RedisKeys.SYNC_ORDERCAST_ORDERS,
            entities=[o["_remote_id"] for o in orders],
        )
        logger.info(f"Syncing only unique orders => {unique_orders}")
        self.odoo_manager.sync_orders(
            [o for o in orders if o["_remote_id"] in unique_orders]
        )

    def sync_orders_with_ordercast(self, from_date: Optional[datetime] = None) -> None:
        ctx = get_ctx()
        orders = self.odoo_manager.receive_orders(
            from_date=from_date,
            orders_invoice_attach_pending=self.odoo_manager.get_orders_invoice_attach_pending(),
        )
        logger.info(
            f"Received {len(orders) if orders else 0} orders, start saving them."
        )
        if orders:
            self.ordercast_manager.sync_orders(
                orders=orders,
                default_price_rate_id=ctx["commons"]["default_price_rate_id"],
                odoo_repo=self.repo,
            )
            self.odoo_manager.save_orders(orders)

    def load_commons(self) -> None:
        default_sector_id = self.ordercast_manager.get_sector()
        default_price_rate_id = self.repo.get_key(RedisKeys.DEFAULT_PRICE_RATE_ID)
        if not default_price_rate_id:
            default_price_rate = self.ordercast_manager.get_default_price_rate()
            default_price_rate_id = default_price_rate["id"]
            self.repo.set(
                key=RedisKeys.DEFAULT_PRICE_RATE_ID, value=default_price_rate_id
            )

        set_context_value(
            value={
                "commons": {
                    "default_sector_id": default_sector_id,
                    "default_price_rate_id": default_price_rate_id,
                }
            }
        )


def get_odoo_sync_manager(
    odoo_repo: Annotated[OdooRepo, Depends(get_odoo_repo)],
    odoo_provider: Annotated[OdooManager, Depends(get_odoo_provider)],
    ordercast_manager: Annotated[OrdercastManager, Depends(get_ordercast_manager)],
) -> OdooSyncManager:
    return OdooSyncManager(
        odoo_repo, odoo_provider, ordercast_manager, WebhookHandler(odoo_provider)
    )
