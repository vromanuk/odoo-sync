import secrets
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Annotated

import structlog
from fastapi import Depends

from src.data import UserStatus, OdooUser, OdooProductGroup, OdooProduct
from .helpers import is_empty, has_objects
from .odoo_manager import OdooManager, get_odoo_provider
from .odoo_repo import OdooRepo, get_odoo_repo, RedisKeys
from .ordercast_manager import OrdercastManager, get_ordercast_manager
from .partner import validate_partners

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
        existing_users = self.repo.get_list(key=RedisKeys.USERS)
        partners = self.odoo_manager.receive_partner_users(
            exclude_user_ids=[p.odoo_id for p in existing_users]
        )
        validate_partners(partners)

        logger.info(f"Received partners => {len(partners)}, started saving them.")

        users_to_sync = [
            {
                "name": partner["name"],
                "erp_id": partner["id"],
                "is_approved": False,
                "is_active": True,
                "is_removed": False,
                "password": secrets.token_urlsafe(nbytes=64),
                "status": UserStatus.NEW,
                "language": partner.get("language", "fr")
                if partner.get("language") and len(partner.get("language")) == 2
                else "fr",
                "website": partner["website"]
                if not is_empty(partner, "website")
                else None,
                "info": partner["comment"]
                if not is_empty(partner, "comment")
                else None,
                "phone": partner.get("phone", ""),
                "city": partner.get("city", ""),
                "postcode": partner.get("postcode", ""),
                "street": partner.get("street", ""),
                "vat": partner.get("vat", ""),
                "odoo_data": partner,
            }
            for partner in partners
            if partner["email"]
        ]

        self.ordercast_manager.upsert_users(users_to_sync=users_to_sync)
        self.repo.insert_many(
            key=RedisKeys.USERS,
            entities=[
                OdooUser(
                    odoo_id=user["id"],
                    sync_date=datetime.now(timezone.utc),
                    user=0,
                )
                for user in users_to_sync
            ],
        )
        self.sync_billing(users=users_to_sync)

    def sync_billing(self, users: list[dict[str, Any]]) -> None:
        for partner in users:
            self.ordercast_manager.update_settings(partner)
            self.ordercast_manager.set_default_language(partner["language"])
            self.ordercast_manager.create_billing_address(partner)
            self.ordercast_manager.create_shipping_address(partner)

    def sync_products(self, full_sync=False):
        # last_sync_date = (
        #     ProductGroupExternal.objects.last_sync_date() if not full_sync else None
        # )
        last_sync_date = (
            None if full_sync else self.repo.get_last_sync_date(OdooProductGroup)
        )
        # groups_dict = self.receive_provider.receive_product_groups(last_sync_date)
        product_groups = self.odoo_manager.get_product_groups(last_sync_date)

        logger.info(f"Connected to Odoo")
        logger.info(
            f"Received {len(product_groups['objects']) if has_objects(product_groups) else 0} groups, start saving them."
        )

        if has_objects(product_groups):
            self.ordercast_manager.save_product_groups(
                product_groups, odoo_repo=self.repo
            )

        # last_sync_date = (
        #     ProductExternal.objects.last_sync_date() if not full_sync else None
        # )
        last_sync_date = (
            None if full_sync else self.repo.get_last_sync_date(OdooProduct)
        )
        products = self.odoo_manager.get_products(last_sync_date)
        has_products = has_objects(products)

        logger.info(
            f"Received {len(products['objects']) if has_products else 0} products."
        )

        if (
            has_products
        ):  # in case when any product is changed sync from begin the categories. bug: when product category changed, but not synced
            category_last_sync_date = None
            logger.info(f"There products are changed, receiving all categories.")
        else:
            category_last_sync_date = self.repo.get_last_sync_date(OdooCategory)

        categories = self.odoo_manager.get_categories(category_last_sync_date)

        logger.info(
            f"Received {len(categories['objects']) if categories['objects'] else 0} categories, start saving them."
        )

        if categories:
            self.ordercast_manager.save_categories(categories)
        if not full_sync:
            last_attribute_name_sync = (
                CategoryExternal.objects.filter(
                    category__category_type=Category.PRODUCT_ATTRIBUTE_TYPE
                )
                .order_by("sync_date")
                .last()
            )
            attribute_category_from_date = None
            if last_attribute_name_sync:
                attribute_category_from_date = last_attribute_name_sync.sync_date

            attributes = self.odoo_manager.get_product_attributes(
                from_date=attribute_category_from_date,
                attribute_from_date=AttributeExternal.objects.last_sync_date(),
            )
        else:
            attributes = self.odoo_manager.get_product_attributes()

        logger.info(
            f"Received {len(attributes['objects']) if attributes['objects'] else 0} attributes with total of {sum([len(a['values']) for a in attributes['objects'] if 'values' in a])} values, start saving them."
        )

        if attributes:
            self.ordercast_manager.save_attributes(attributes, odoo_repo=self.repo)

        if has_products:
            logger.info(
                f"Starting saving products after saving categories and attributes."
            )
            self.ordercast_manager.save_products(
                categories, product_groups, attributes, products, odoo_repo=self.repo
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
) -> OdooSyncManager:
    return OdooSyncManager(odoo_repo, odoo_provider, ordercast_manager)
