from datetime import datetime, timezone
from typing import Annotated, Any, Optional

import structlog
from fastapi import Depends

from src.data import (
    OdooOrder,
    InvoiceStatus,
    OrderStatus,
    Locale,
    OrdercastFlatMerchant,
    OrdercastProduct,
    OrdercastAttribute,
    OrdercastCategory,
    OrdercastFlatOrder,
    OrdercastOrderStatus,
    OrdercastOrder,
)
from src.infrastructure import (
    OrdercastApi,
    get_ordercast_api,
    CreateShippingAddressRequest,
    ListBillingAddressesRequest,
    ListShippingAddressesRequest,
    CreateOrderRequest,
    BulkSignUpRequest,
    UpdateSettingsRequest,
    CreateBillingAddressRequest,
    ListMerchantsRequest,
    UpsertProductsRequest,
    UpsertCategoriesRequest,
    UpsertAttributesRequest,
    Merchant,
    UpsertProductVariantsRequest,
    UpsertUnitsRequest,
    I18Name,
    ListProductsRequest,
    UpsertPriceRatesRequest,
    PriceRate,
    AddDeliveryMethodRequest,
    CreatePickupLocationRequest,
    ListOrdersRequest,
)
from .constants import ORDER_STATUSES_FOR_SYNC
from .odoo_repo import RedisKeys, OdooRepo

logger = structlog.getLogger(__name__)


class OrdercastManager:
    def __init__(self, ordercast_api: OrdercastApi) -> None:
        self.ordercast_api = ordercast_api

    def get_users(self) -> list[OrdercastFlatMerchant]:
        # TODO: handle pagination
        response = self.ordercast_api.get_merchants(request=ListMerchantsRequest())
        users = response.json()["items"]
        return [
            OrdercastFlatMerchant(
                id=user["id"], name=user["name"], erp_id=user["erp_id"]
            )
            for user in users
        ]

    def upsert_users(self, users_to_sync: list[dict[str, Any]]) -> None:
        default_sector_id = self.get_sector()
        self.ordercast_api.bulk_signup(
            [
                BulkSignUpRequest(
                    merchant=Merchant(
                        erp_id=user["erp_id"],
                        name=user["name"],
                        phone=user["phone"],
                        city=user["city"],
                        sector_id=user.get("sector_id", default_sector_id),
                        postcode=user["postcode"],
                        street=user["street"],
                        vat=user["vat"],
                        website=user["website"],
                        info=user["info"],
                        corporate_status_id=user.get("corporate_status_id", 1),
                        country_alpha_2=user.get("country_alpha_2", "GB"),
                    )
                )
                for user in users_to_sync
            ]
        )

    def create_billing_address(self, user: dict[str, Any]) -> None:
        for billing_address in user["odoo_data"]["billing_addresses"]:
            self.ordercast_api.create_billing_address(
                CreateBillingAddressRequest(
                    merchant_id=user["merchant_id"],
                    name=user["name"],
                    street=user["street"],
                    city=user["city"],
                    postcode=user["postcode"],
                    country=user["country"],
                    contact_name=user["contact_name"],
                    contact_phone=user["contact_phone"],
                    corporate_status_name=user["corporate_status_name"],
                    vat=user["vat"],
                )
            )

    def create_shipping_address(
        self,
        user: dict[str, Any],
    ) -> None:
        for shipping_address in user["odoo_data"]["shipping_addresses"]:
            self.ordercast_api.create_shipping_address(
                CreateShippingAddressRequest(
                    merchange_id=user["id"],
                    name=user["name"],
                    street=user["street"],
                    city=user["city"],
                    postcode=user["postcode"],
                    country=user["country"],
                    contact_name=user["contact_name"],
                    contact_phone=user["contact_phone"],
                )
            )

    def get_billing_addresses(self, merchant_id: int) -> list[dict[str, Any]]:
        response = self.ordercast_api.list_billing_addresses(
            ListBillingAddressesRequest(merchant_id=merchant_id)
        )
        return response.json()

    def get_shipping_addresses(self, merchant_id: int) -> list[dict[str, Any]]:
        response = self.ordercast_api.list_shipping_addresses(
            ListShippingAddressesRequest(merchant_id=merchant_id)
        )
        return response.json()

    def set_default_language(self, locale: Locale) -> None:
        self.ordercast_api.update_default_language(locale)

    def update_settings(self, settings: dict[str, str]) -> None:
        self.ordercast_api.update_settings(
            UpdateSettingsRequest(
                url=settings.get("website", ""),
                extra_phone=settings.get("extra_phone", ""),
                fax=settings.get("fax", ""),
                payment_info=settings.get("payment_info", ""),
            )
        )

    def get_sector(self) -> id:
        response = self.ordercast_api.list_sectors()
        sectors = response.json()

        return sectors[0]["id"]

    def get_catalog(self) -> int:
        response = self.ordercast_api.list_catalogs()
        catalogs = response.json()

        return catalogs[0]["id"]

    def get_products(self) -> list[OrdercastProduct]:
        logger.info("Receiving products from Ordercast")
        # TODO: handle pagination
        response = self.ordercast_api.get_products(request=ListProductsRequest())
        result_json = response.json()
        if result_json:
            return [
                OrdercastProduct(
                    id=product["id"], sku=product["sku"], name=product["name"]
                )
                for product in result_json["items"]
            ]
        return []

    def get_attributes(self) -> list[OrdercastAttribute]:
        logger.info("Receiving attributes from Ordercast")
        response = self.ordercast_api.get_attributes()
        return [
            OrdercastAttribute(id=attribute["id"], name=attribute["name"])
            for attribute in response.json()
        ]

    def get_categories(self) -> list[OrdercastCategory]:
        logger.info("Receiving categories from Ordercast")
        response = self.ordercast_api.get_categories()
        return [
            OrdercastCategory(
                id=category["id"], name=category["name"], code=category["code"]
            )
            for category in response.json()
        ]

    def get_default_price_rate(self) -> dict[str, Any]:
        logger.info("Creating a Default Odoo price rate")
        default_odoo_price_rate = "Default Odoo Price Rate"
        self.ordercast_api.upsert_price_rate(
            request=UpsertPriceRatesRequest(name=default_odoo_price_rate)
        )
        logger.info("Created a Default Odoo price rate")

        logger.info("Receiving `id` of Default Odoo price rate")
        response = self.ordercast_api.get_price_rates()
        result_json = response.json()
        return next(
            (
                price_rate
                for price_rate in result_json
                if price_rate.get("name") == default_odoo_price_rate
            ),
            None,
        )

    def save_products(self, products: list[dict[str, Any]]) -> None:
        default_catalog = self.get_catalog()
        self.ordercast_api.upsert_products(
            request=[
                UpsertProductsRequest(
                    name=product["names"],
                    sku=product.get("sku", product["name"]),
                    catalogs=[{"catalog_id": default_catalog}],
                    categories=[{"category_id": product["category"]}],
                )
                for product in products
            ]
        )

    def save_categories(self, categories: list[dict[str, Any]]) -> None:
        self.ordercast_api.upsert_categories(
            request=[
                UpsertCategoriesRequest(
                    name=category["names"],
                    parent_code=category["parent_code"],
                    index=category.get("index", 1),
                    code=category.get("code", ""),
                )
                for category in categories
            ]
        )

    def save_attributes(self, attributes_to_sync: list[dict[str, Any]]) -> None:
        self.ordercast_api.upsert_attributes(
            request=[
                UpsertAttributesRequest(
                    code=str(attribute["id"]), name=attribute["name"]
                )  # TODO: fix code
                for attribute in attributes_to_sync
            ]
        )

    def save_product_variants(
        self,
        product_variants: list[dict[str, Any]],
        units: list[dict[str, Any]],
        default_price_rate: dict[str, Any],
    ) -> None:
        # TODO fetch from cache if exists
        logger.info(f"Inserting units from product variants => {len(units)}")
        self.ordercast_api.upsert_units(
            request=[
                UpsertUnitsRequest(code=unit["code"], name=I18Name(names=unit["names"]))
                for unit in units
            ]
        )
        logger.info("Inserted / updated units from product variants")

        logger.info(f"Inserting product variants => {len(product_variants)}")
        self.ordercast_api.upsert_product_variants(
            request=[
                UpsertProductVariantsRequest(
                    name=product_variant["names"],
                    barcode=product_variant.get(
                        "barcode", product_variant.get("ref", "")
                    ),
                    product_id=product_variant["product_id"],
                    sku=product_variant["sku"],
                    price_rates=[
                        PriceRate(
                            price=product_variant["price"],
                            price_rate_id=default_price_rate["id"],
                            quantity=1,
                        )
                    ],
                    unit_code=product_variant["unit_code"],
                    attribute_values=[
                        {"value_id": a.id}
                        for a in product_variant["attribute_values"]
                        if a
                    ],
                    place_in_warehouse="",
                    customs_code="",
                    letter="",
                    description=product_variant.get("description", ""),
                )
                for product_variant in product_variants
            ]
        )

    def save_delivery_options(self, delivery_options: list[dict[str, Any]]) -> None:
        logger.info("Adding delivery options to Ordercast")
        for delivery_option in delivery_options:
            self.ordercast_api.add_delivery_method(
                request=AddDeliveryMethodRequest(
                    name=I18Name(names=delivery_option["names"])
                )
            )

    def save_pickup_locations(self, pickup_locations: list[dict[str, Any]]) -> None:
        logger.info("Adding pickup locations to Ordercast")
        for pickup_location in pickup_locations:
            self.ordercast_api.add_pickup_location(
                request=CreatePickupLocationRequest(
                    name=I18Name(names=pickup_location["names"]),
                    street=pickup_location["partner"]["street"],
                    city=pickup_location["partner"]["city"],
                    postcode=pickup_location["partner"]["postcode"],
                    country=pickup_location["partner"]["country"],
                    contact_name=pickup_location["partner"]["contact_name"],
                    contact_phone=pickup_location["partner"]["contact_phone"],
                )
            )

    def get_order_statuses(self) -> list[OrdercastOrderStatus]:
        logger.info("Receiving order statuses from Ordercast")

        response = self.ordercast_api.get_order_statuses()

        logger.info(f"Received {len(response.json())} order statuses from Ordercast")

        return [
            OrdercastOrderStatus(
                id=status["id"], name=status["name"], enum=status["enum"]
            )
            for status in response.json()
        ]

    def get_orders(
        self,
        statuses: list[OrdercastOrderStatus],
        order_ids: Optional[list[int]] = None,
        from_date: Optional[datetime] = None,
    ) -> list[OrdercastFlatOrder]:
        status_ids = [
            status.id for status in statuses if status.enum in ORDER_STATUSES_FOR_SYNC
        ]

        logger.info("Receiving orders from Ordercast")

        # TODO handle pagination
        response = self.ordercast_api.get_orders_for_sync(
            request=ListOrdersRequest(
                statuses=status_ids, order_ids=order_ids, from_date=from_date
            )
        )
        result_json = response.json()

        logger.info(f"Received {len(result_json['items'])} orders to sync")

        return [OrdercastFlatOrder(**order) for order in result_json["items"]]

    def get_orders_for_sync(
        self,
        odoo_repo: OdooRepo,
        order_ids: Optional[list[int]] = None,
        from_date: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        statuses = self.get_order_statuses()

        orders_to_sync = self.get_orders(
            statuses=statuses, order_ids=order_ids, from_date=from_date
        )

        result = []
        for order in orders_to_sync:
            ordercast_order = OrdercastOrder(
                **self.ordercast_api.get_order(order.id).json()
            )
            order_dto = {
                "id": order.id,
                "name": f"OC{str(order.id).zfill(5)}",
                "status": order.status,
                "_remote_id": order.external_id,
                "user_remote_id": ordercast_order.merchant.external_id,
            }
            if order.shipping_address:
                order_dto["shipping_address"] = order.shipping_address
            if ordercast_order.billing_address:
                order_dto["billing_address"] = ordercast_order.billing_address
            if order.delivery_method:
                delivery_option = order.delivery_option
                delivery_option_dto = {
                    "id": delivery_option.id,
                    "name": delivery_option.name,
                }
                odoo_delivery_option = odoo_repo.get(
                    key=RedisKeys.DELIVERY_OPTIONS, entity_id=delivery_option.id
                )
                if odoo_delivery_option:
                    delivery_option_dto["_remote_id"] = odoo_delivery_option.odoo_id

                order_dto["delivery_option"] = delivery_option_dto
            if order.pickup_location:
                warehouse = order.pickup_location
                warehouse_dto = {"id": warehouse.id, "name": warehouse.name}
                odoo_warehouse = odoo_repo.get(
                    key=RedisKeys.PICKUP_LOCATIONS, entity_id=warehouse.id
                )
                if odoo_warehouse:
                    warehouse_dto["_remote_id"] = odoo_warehouse.odoo_id
                else:
                    logger.info(
                        f"The warehouse name '{warehouse.name}' has no remote id."
                        f"Please sync it first with Odoo."
                    )
                order_dto["warehouse"] = warehouse_dto

            if ordercast_order.invoice:
                order_dto["invoice_number"] = ordercast_order.invoice.get(
                    "invoice_number", 0
                )
            if ordercast_order.note:
                order_dto["note"] = ordercast_order.note

            result.append(order_dto)

        return result

    def sync_orders(self, orders: list[dict[str, Any]]) -> None:
        for order in orders:
            odoo_order = odoo_repo.get(key=RedisKeys.ORDERS, entity_id=order["id"])
            if odoo_order:
                odoo_order.odoo_order_status = order["status"]
                odoo_order.odoo_invoice_status = order["invoice_status"]

                existing_order = odoo_order.order
                if "invoice_file_data" in order:
                    # self.save_file(order['invoice_file_name'], order['invoice_file_data'], existing_order.invoice)
                    logger.info(
                        f"Invoice file {order['invoice_file_name']} "
                        f"added for order {existing_order.id}."
                    )
                elif existing_order.invoice:
                    logger.info(
                        f"""
                        Invoice file {existing_order.invoice.url.split('/')[-1]
                        if existing_order.invoice and existing_order.invoice.url else ''} 
                        removed from order {existing_order.id}.
                        """
                    )
                    # self.delete_file(existing_order.invoice)

                if "note" in order:
                    existing_order.note = order["note"]

                odoo_repo.insert(
                    key=RedisKeys.ORDERS,
                    entity=OdooOrder(
                        odoo_id=existing_order.odoo_id,
                        order=existing_order.order,
                        sync_date=datetime.now(timezone.utc),
                        odoo_order_status=existing_order.odoo_order_status,
                        odoo_invoice_status=existing_order.odoo_invoice_status,
                    ),
                )

                self.ordercast_api.create_order(
                    CreateOrderRequest(
                        order_status_enum=existing_order.odoo_order_status,
                        merchant_id=None,
                        price_rate_id=None,
                        external_id=existing_order.odoo_id,
                    )
                )
                self.update_order_status(existing_order, odoo_order, order)
            else:
                logger.error(
                    f"Address with remote_id={order['id']} "
                    f"not exists in the system, please run sync task first."
                )

    def update_order_status(self, existing_order, external_order, order):
        # TODO: fix
        try:
            if (
                external_order.odoo_invoice_status == InvoiceStatus.INV_INVOICED_STATUS
                and existing_order.status
                not in [
                    OrderStatus.PROCESSED_STATUS,
                    OrderStatus.PENDING_PAYMENT_STATUS,
                    OrderStatus.CANCELLED_BY_ADMIN_STATUS,
                ]
            ):
                logger.info(
                    f"""
                    Order '{order['name']}' has Odoo oder status: 
                    '{external_order.odoo_order_status}' and 
                    invoice status: '{external_order.odoo_invoice_status}', 
                    updating to 'Processed'.
                    """
                )
                if existing_order.invoice:
                    url = utils.get_invoice_full_url(existing_order.invoice)
                    existing_order.processed(url)
                else:
                    logger.warn(
                        f"Order '{order['name']}' has no invoice file, "
                        f"so changing status to 'Processed' ignored."
                    )
            elif (
                external_order.odoo_order_status == OrderStatus.DONE_STATUS
                and existing_order.status != OrderStatus.COMPLETED_STATUS
            ):
                logger.info(
                    f"""
                    Order '{order['name']}' has Odoo oder status:
                    '{external_order.odoo_order_status}' and 
                    invoice status: '{external_order.odoo_invoice_status}',
                    updating to 'Completed'.
                    """
                )
                existing_order.complete()
            elif (
                external_order.odoo_order_status == OrderStatus.CANCEL_STATUS
                and existing_order.status != OrderStatus.CANCELLED_BY_ADMIN_STATUS
            ):
                logger.info(
                    f"""
                    Order '{order['name']}' has Odoo oder status:
                    '{external_order.odoo_order_status}' and 
                    invoice status: '{external_order.odoo_invoice_status}',
                    updating to 'Cancelled'.
                    """
                )
                if existing_order.status in [
                    OrderStatus.SUBMITTED_STATUS,
                    OrderStatus.IN_PROGRESS_STATUS,
                ]:
                    existing_order.cancel(existing_order.operator)
                else:
                    logger.warn(
                        f"""
                        Order {order['name']} can not be cancelled, 
                        since it has '{existing_order.status}' status
                        and only orders with {OrderStatus.SUBMITTED_STATUS}
                        or {OrderStatus.IN_PROGRESS_STATUS}'
                        statuses permitted to cancel.
                        """
                    )
            existing_order.save()
        except Exception as exc:
            logger.error("Error during updating order status locally.")
            raise exc


def get_ordercast_manager(
    ordercast_api: Annotated[OrdercastApi, Depends(get_ordercast_api)]
) -> OrdercastManager:
    return OrdercastManager(ordercast_api)
