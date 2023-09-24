from datetime import datetime
from typing import Any, Annotated, Optional

import structlog
from fastapi import Depends

from src.data import (
    OdooPriceRate,
)
from .internal.builders import (
    get_partner_data,
    get_attribute_data,
    get_product_data,
    get_product_variant_data,
    get_delivery_option_data,
    get_pickup_location_data,
)
from .internal.helpers import has_objects
from .internal.odoo_manager import OdooManager, get_odoo_provider
from .internal.odoo_repo import OdooRepo, get_odoo_repo, RedisKeys
from .internal.ordercast_manager import OrdercastManager, get_ordercast_manager
from .internal.partner import validate_partners
from .internal.validators import (
    validate_products,
    validate_categories,
    validate_product_variants,
    validate_attributes,
    validate_delivery_options,
    validate_pickup_locations,
)

logger = structlog.getLogger(__name__)


class OdooSyncManager:
    def __init__(
        self,
        repo: OdooRepo,
        odoo_manager: OdooManager,
        ordercast_manager: OrdercastManager,
    ) -> None:
        self.repo = repo
        self.odoo_manager = odoo_manager
        self.ordercast_manager = ordercast_manager

    def sync(self) -> None:
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
        logger.info("Start sync orders with Ordercast")
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
            exclude_user_ids=[p.odoo_id for p in existing_odoo_users]
        )
        validate_partners(
            partners=partners, ordercast_users=self.ordercast_manager.get_users()
        )

        logger.info(f"Received partners => {len(partners)}, started saving them.")

        users_to_sync = [
            get_partner_data(partner) for partner in partners if partner["email"]
        ]

        self.ordercast_manager.upsert_users(users_to_sync=users_to_sync)
        self.odoo_manager.save_users(users_to_sync=users_to_sync)
        self.sync_billing(users=users_to_sync)

    def sync_users_from_ordercast_to_odoo(self) -> None:
        users_to_sync = self.ordercast_manager.get_users_with_related_entities()
        logger.info(
            f"Received merchants => {len(users_to_sync)}, started syncing with Odoo."
        )
        self.odoo_manager.sync_users(users_to_sync)

    def sync_billing(self, users: list[dict[str, Any]]) -> None:
        for partner in users:
            self.ordercast_manager.create_billing_address(partner)
            self.ordercast_manager.create_shipping_address(partner)

    def sync_products(self, full_sync: bool = False) -> None:
        categories = self.sync_categories_to_ordercast()
        attributes = self.sync_attributes_to_ordercast()
        products = self.sync_products_to_ordercast(
            categories=categories["objects"], full_sync=full_sync
        )
        self.sync_product_variants_to_ordercast(
            full_sync=full_sync,
            products=products["objects"],
            attributes=attributes["objects"],
        )

    def sync_categories_to_ordercast(self) -> dict[str, Any]:
        categories = self.odoo_manager.get_categories()
        logger.info(
            f"""
            Received {len(categories['objects']) if categories['objects'] else 0} 
            categories, start saving them.
            """
        )
        if categories:
            validate_categories(categories)
            self.ordercast_manager.save_categories(categories["objects"])
            self.odoo_manager.save_categories(categories["objects"])

        return categories

    def sync_attributes_to_ordercast(self) -> dict[str, Any]:
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
                get_attribute_data(value)
                for attribute in attributes["objects"]
                for value in attribute.get("values", [])
                if all(key in value for key in ("id", "name"))
            ]

            self.ordercast_manager.save_attributes(
                attributes_to_sync=attributes_to_sync
            )
            self.odoo_manager.save_attributes(attributes_to_sync)

        return attributes

    def sync_products_to_ordercast(
        self, categories: list[dict[str, Any]], full_sync: bool = False
    ) -> dict[str, Any]:
        last_sync_date = (
            None if full_sync else self.repo.get_key(RedisKeys.LAST_PRODUCT_SYNC)
        )
        products = self.odoo_manager.get_products(last_sync_date)

        logger.info("Connected to Odoo")
        logger.info(
            f"Received {len(products['objects']) if has_objects(products) else 0} "
            f"products, start saving them."
        )

        if has_objects(products):
            validate_products(products)

            ordercast_categories = self.ordercast_manager.get_categories()

            products_to_sync = [
                get_product_data(
                    product,
                    odoo_categories=categories,
                    ordercast_categories=ordercast_categories,
                )
                for product in products["objects"]
            ]

            self.ordercast_manager.save_products(products_to_sync)
            self.odoo_manager.save_products(products_to_sync)

        return products

    def sync_product_variants_to_ordercast(
        self,
        products: list[dict[str, Any]],
        attributes: list[dict[str, Any]],
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
            f"Received {len(product_variants['objects']) if has_product_variants else 0}"
            f"products variants."
        )

        if has_product_variants:
            validate_product_variants(product_variants["objects"])
            logger.info(
                "Starting saving product variants after"
                "saving categories and attributes."
            )
            default_price_rate = self.repo.get_key(RedisKeys.DEFAULT_PRICE_RATE)

            if not default_price_rate:
                default_price_rate = self.ordercast_manager.get_default_price_rate()
                self.repo.set(
                    key=RedisKeys.DEFAULT_PRICE_RATE,
                    entity=OdooPriceRate(
                        id=default_price_rate["id"], name=default_price_rate["name"]
                    ),
                )

            units = self.odoo_manager.get_units()
            ordercast_products = self.ordercast_manager.get_products()
            ordercast_attributes = self.ordercast_manager.get_attributes()
            product_variants_to_sync = [
                get_product_variant_data(
                    product_variant=product_variant,
                    odoo_products=products,
                    ordercast_products=ordercast_products,
                    odoo_attributes=attributes,
                    ordercast_attributes=ordercast_attributes,
                )
                for product_variant in product_variants["objects"]
            ]

            self.ordercast_manager.save_product_variants(
                product_variants=product_variants_to_sync,
                units=units,
                default_price_rate=default_price_rate,
            )
            self.odoo_manager.save_product_variants(product_variants_to_sync)

    def sync_delivery_methods_and_pickup_locations(self) -> None:
        delivery_options = self.odoo_manager.receive_delivery_options()
        logger.info(
            f"Received {len(delivery_options['objects']) if has_objects(delivery_options) else 0}"
            f"delivery options, start saving them."
        )
        if delivery_options:
            validate_delivery_options(delivery_options)

            delivery_options_to_sync = [
                get_delivery_option_data(delivery_option)
                for delivery_option in delivery_options["objects"]
            ]

            self.ordercast_manager.save_delivery_options(delivery_options_to_sync)
            self.odoo_manager.save_delivery_options(delivery_options_to_sync)

        else:
            # TODO: enable
            pass
            # existing_odoo_delivery_options = self.repo.get_list(
            #     key=RedisKeys.DELIVERY_OPTIONS
            # )
            # existing_ordercast_delivery_options = set()
            # to_delete = (
            #     existing_ordercast_delivery_options - existing_odoo_delivery_options
            # )
            # self.ordercast_manager.delete_delivery_options(to_delete)
            # self.repo.remove(to_delete)

        pickup_locations = self.odoo_manager.receive_pickup_locations(
            partners=self.repo.get_list(RedisKeys.USERS)
        )
        logger.info(
            f"Received {len(pickup_locations['objects']) if has_objects(pickup_locations) else 0}"
            f"warehouses, start saving them."
        )
        if pickup_locations:
            validate_pickup_locations(pickup_locations)

            pickup_locations_to_sync = [
                get_pickup_location_data(pickup_location)
                for pickup_location in pickup_locations["objects"]
            ]

            self.ordercast_manager.save_pickup_locations(pickup_locations_to_sync)
            self.odoo_manager.save_pickup_locations(pickup_locations_to_sync)

    def sync_orders_with_odoo(
        self,
        order_ids: Optional[list[int]] = None,
        from_date: Optional[datetime] = None,
    ) -> None:
        orders = self.ordercast_manager.get_orders_for_sync(
            odoo_repo=self.repo, order_ids=order_ids, from_date=from_date
        )
        logger.info(f"Loaded {len(orders)} orders, start sending them to Odoo.")
        self.odoo_manager.sync_orders(orders)

    def sync_orders_with_ordercast(self, from_date: Optional[datetime] = None) -> None:
        orders = self.odoo_manager.receive_orders(
            from_date=from_date,
            orders_invoice_attach_pending=self.odoo_manager.get_orders_invoice_attach_pending(),
        )
        logger.info(
            f"Received {len(orders) if orders else 0} orders, start saving them."
        )
        if orders:
            self.ordercast_manager.sync_orders(orders)


def get_odoo_sync_manager(
    odoo_repo: Annotated[OdooRepo, Depends(get_odoo_repo)],
    odoo_provider: Annotated[OdooManager, Depends(get_odoo_provider)],
    ordercast_manager: Annotated[OrdercastManager, Depends(get_ordercast_manager)],
) -> OdooSyncManager:
    return OdooSyncManager(odoo_repo, odoo_provider, ordercast_manager)
