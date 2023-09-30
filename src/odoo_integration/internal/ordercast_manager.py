import base64
from datetime import datetime
from typing import Annotated, Any, Optional

import structlog
from fastapi import Depends

from src.commons import get_ctx
from src.data import (
    Locale,
    OrdercastFlatMerchant,
    OrdercastProduct,
    OrdercastAttribute,
    OrdercastCategory,
    OrdercastFlatOrder,
    OrdercastOrderStatus,
    OrdercastOrder,
    OrderStatusForSync,
    OrdercastAttributeValue,
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
    Employee,
    OrdercastApiValidationException,
    paginated,
    UpsertAttributeValuesRequest,
)
from .constants import ORDER_STATUSES_FOR_SYNC
from .odoo_repo import RedisKeys, OdooRepo
from .utils import slugify

logger = structlog.getLogger(__name__)


class OrdercastManager:
    def __init__(self, ordercast_api: OrdercastApi) -> None:
        self.ordercast_api = ordercast_api

    def get_users(self) -> list[OrdercastFlatMerchant]:
        users = paginated(
            self.ordercast_api.get_merchants, request=ListMerchantsRequest()
        )
        return [
            OrdercastFlatMerchant(
                id=user["id"], name=user["name"], erp_id=user["erp_id"]
            )
            for user in users
        ]

    def upsert_users(self, users_to_sync: list[dict[str, Any]]) -> None:
        ctx = get_ctx()
        logger.info("Saving users to Ordercast")
        self.ordercast_api.bulk_signup(
            request=[
                BulkSignUpRequest(
                    employee=Employee(
                        email=user["email"],
                        first_name=user["name"],
                        last_name=user["name"],
                        phone=user["phone"],
                        password=user["password"],
                        language=user["language"],
                    ),
                    merchant=Merchant(
                        erp_id=user["erp_id"],
                        name=user["name"],
                        phone=user["phone"],
                        city=user["city"],
                        sector_id=user.get(
                            "sector_id", ctx["commons"]["default_sector_id"]
                        ),
                        price_rate_id=ctx["commons"]["default_price_rate"]["id"],
                        postcode=user["postcode"],
                        street=user["street"],
                        vat=user["vat"],
                        website=user["website"],
                        info=user["info"],
                        country_alpha_2=user.get("country_alpha_2", "GB"),
                    ),
                )
                for user in users_to_sync
            ]
        )

    def create_billing_address(self, user: dict[str, Any]) -> None:
        logger.info("Creating billing address")
        try:
            for billing_address in user["odoo_data"]["billing_addresses"]:
                self.ordercast_api.create_billing_address(
                    CreateBillingAddressRequest(
                        merchant_id=user["ordercast_id"],
                        name=billing_address["name"],
                        street=billing_address["address_one"],
                        city=billing_address["city"],
                        postcode=billing_address["postal_code"],
                        country=billing_address["country"],
                        contact_name=billing_address["name"],
                        contact_phone=billing_address.get("phone", "3281000000"),
                        corporate_status_name=billing_address["name"],
                        vat=user["vat"],
                    )
                )
        except OrdercastApiValidationException as e:
            logger.error(f"Error during billing address creation => {e}, skipping")

    def create_shipping_address(
        self,
        user: dict[str, Any],
    ) -> None:
        logger.info("Creating shipping address")
        try:
            for shipping_address in user["odoo_data"]["shipping_addresses"]:
                self.ordercast_api.create_shipping_address(
                    CreateShippingAddressRequest(
                        merchant_id=user["ordercast_id"],
                        name=shipping_address["name"],
                        street=shipping_address["address_one"],
                        city=shipping_address["city"],
                        postcode=shipping_address["postal_code"],
                        country=shipping_address["country"],
                        contact_name=shipping_address["name"],
                        contact_phone=shipping_address["phone"],
                        corporate_status_name=shipping_address["name"],
                    )
                )
        except OrdercastApiValidationException as e:
            logger.error(f"Error during shipping address creation => {e}, skipping")

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

    def get_sector(self) -> int:
        response = self.ordercast_api.list_sectors()
        sectors = response.json()

        return sectors[0]["id"]

    def get_catalog(self) -> int:
        response = self.ordercast_api.list_catalogs()
        catalogs = response.json()

        return catalogs[0]["id"]

    def get_products(self) -> list[OrdercastProduct]:
        logger.info("Receiving products from Ordercast")
        products = paginated(
            self.ordercast_api.get_products, request=ListProductsRequest()
        )
        return [
            OrdercastProduct(id=product["id"], sku=product["sku"], name=product["name"])
            for product in products
        ]

    def get_attributes(self) -> list[OrdercastAttribute]:
        logger.info("Receiving attributes from Ordercast")
        response = self.ordercast_api.get_attributes()
        return [
            OrdercastAttribute(
                id=attribute["id"], name=attribute["name"], code=attribute["code"]
            )
            for attribute in response.json()
        ]

    def get_attribute_values(self, attribute_id: int) -> list[OrdercastAttributeValue]:
        logger.info("Receiving attribute values from Ordercast")
        response = self.ordercast_api.get_attribute_values(attribute_id=attribute_id)
        return [
            OrdercastAttributeValue(id=attribute["id"], name=attribute["name"])
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
            request=[UpsertPriceRatesRequest(name=default_odoo_price_rate)]
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

    def save_products(self, products_to_sync: list[dict[str, Any]]) -> None:
        default_catalog = self.get_catalog()
        self.ordercast_api.upsert_products(
            request=[
                UpsertProductsRequest(
                    name=product["names"],
                    sku=product.get("sku", slugify(product["name"])),
                    catalogs=[{"catalog_id": default_catalog}],
                    categories=[{"category_id": product["category"].category}],
                )
                for product in products_to_sync
                if product.get("category")
            ]
        )
        skipped_products = [
            product["name"]
            for product in products_to_sync
            if not product.get("category")
        ]
        logger.warn(f"Skipped products {skipped_products} that don't have a category")

    def save_categories(self, categories_to_sync: list[dict[str, Any]]) -> None:
        self.ordercast_api.upsert_categories(
            request=[
                UpsertCategoriesRequest(
                    name=category["names"],
                    parent_code=slugify(category["parent_code"]),
                    index=category.get("index", 1),
                    code=slugify(category["name"]),
                )
                for category in categories_to_sync
            ]
        )

    def save_attributes(self, attributes_to_sync: list[dict[str, Any]]) -> None:
        self.ordercast_api.upsert_attributes(
            request=[
                UpsertAttributesRequest(
                    code=slugify(attribute["name"]),
                    name=I18Name(names=attribute["names"]),
                )
                for attribute in attributes_to_sync
            ]
        )

    def save_product_variants(
        self,
        product_variants: list[dict[str, Any]],
        units: list[dict[str, Any]],
    ) -> None:
        ctx = get_ctx()
        logger.info(f"Inserting units from product variants => {len(units)}")
        self.ordercast_api.upsert_units(
            request=[
                UpsertUnitsRequest(
                    code=slugify(unit["code"]), name=I18Name(names=unit["names"])
                )
                for unit in units
            ]
        )
        logger.info("Inserted / updated units from product variants")

        logger.info(f"Inserting product variants => {len(product_variants)}")
        self.ordercast_api.upsert_product_variants(
            request=[
                UpsertProductVariantsRequest(
                    name=I18Name(names=product_variant["names"]),
                    barcode={
                        "code": product_variant.get(
                            "barcode", product_variant.get("ref", "")
                        )
                    },
                    product_id=product_variant["product"].product,
                    parent_product_id=product_variant["product"].product,
                    sku=product_variant["sku"],
                    price_rates=[
                        PriceRate(
                            price=product_variant["price"],
                            price_rate_id=ctx["commons"]["default_price_rate"]["id"],
                            quantity=1,
                        )
                    ],
                    unit_code=slugify(product_variant["unit"]),
                    attribute_values=[
                        {"value_id": a.attribute}
                        for a in product_variant["attribute_values"]
                    ],
                    place_in_warehouse="",
                    customs_code="",
                    letter="",
                    description=product_variant.get("description", ""),
                )
                for product_variant in product_variants
                if product_variant["product"]
            ]
        )
        skipped_product_variants = [
            pv["name"] for pv in product_variants if not pv["product"]
        ]
        logger.warn(
            f"Skipping product variants {skipped_product_variants} without product"
        )

    def save_delivery_options(self, delivery_options: list[dict[str, Any]]) -> None:
        logger.info("Adding delivery options to Ordercast")
        for delivery_option in delivery_options:
            self.ordercast_api.add_delivery_method(
                request=AddDeliveryMethodRequest(
                    name=I18Name(names=delivery_option["names"])
                )
            )

    def save_pickup_locations(
        self, pickup_locations_to_sync: list[dict[str, Any]]
    ) -> None:
        logger.info("Adding pickup locations to Ordercast")
        for pickup_location in pickup_locations_to_sync:
            self.ordercast_api.add_pickup_location(
                request=CreatePickupLocationRequest(
                    name=I18Name(names=pickup_location["names"]),
                    street=pickup_location["partner"].street,
                    city=pickup_location["partner"].city,
                    postcode=pickup_location["partner"].postcode,
                    country=pickup_location["partner"].country,
                    contact_name=pickup_location["partner"].contact_name,
                    contact_phone=pickup_location["partner"].contact_phone,
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

        orders = paginated(
            self.ordercast_api.get_orders_for_sync,
            request=ListOrdersRequest(
                statuses=status_ids, order_ids=order_ids, from_date=from_date
            ),
        )

        return [OrdercastFlatOrder(**order) for order in orders]

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

    def sync_orders(
        self,
        orders: list[dict[str, Any]],
        default_price_rate: dict[str, Any],
        odoo_repo: OdooRepo,
    ) -> None:
        for order in orders:
            ordercast_order_id = self.ordercast_api.create_order(
                request=CreateOrderRequest(
                    order_status_enum=OrderStatusForSync.ordercast_to_odoo_status_map(
                        order["status"]
                    ).value,
                    merchant_id=odoo_repo.get(
                        RedisKeys.USERS, order["partner_id"]
                    ).ordercast_user,
                    price_rate_id=default_price_rate["id"],
                    external_id=order["id"],
                )
            )

            if file_content := order.get("invoice_file_data"):
                response = self.ordercast_api.get_order(ordercast_order_id)
                ordercast_order_internal_id = response.json()["internal_id"]
                self.ordercast_api.attach_invoice(
                    order_id=ordercast_order_id,
                    filename=ordercast_order_internal_id + order["invoice_file_name"],
                    file_content=base64.b64decode(file_content),
                )
                logger.info(f"Invoice file attached to order {ordercast_order_id}")

    def get_users_with_related_entities(self) -> list[OrdercastFlatMerchant]:
        users = self.get_users()
        billing_addresses = {m.id: self.get_billing_addresses(m.id) for m in users}
        shipping_addresses = {m.id: self.get_shipping_addresses(m.id) for m in users}

        for user in users:
            user.billing_addresses = billing_addresses.get(user.id, [])
            user.shipping_addresses = shipping_addresses.get(user.id, [])

        return users

    def save_attribute_values(
        self,
        attributes_odoo_to_ordercast_mapper: dict[int, int],
        attribute_values_to_sync: dict[int, Any],
    ) -> None:
        for attribute_id, attribute_values in attribute_values_to_sync.items():
            self.ordercast_api.upsert_attribute_values(
                attribute_id=attributes_odoo_to_ordercast_mapper[attribute_id],
                request=[
                    UpsertAttributeValuesRequest(name=attribute_value["name"])
                    for attribute_value in attribute_values
                ],
            )


def get_ordercast_manager(
    ordercast_api: Annotated[OrdercastApi, Depends(get_ordercast_api)]
) -> OrdercastManager:
    return OrdercastManager(ordercast_api)
