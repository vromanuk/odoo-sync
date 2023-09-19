from datetime import datetime, timezone
from typing import Annotated, Any

import structlog
from fastapi import Depends

from src.data import (
    OdooDeliveryOption,
    OdooWarehouse,
    OdooOrder,
    InvoiceStatus,
    OrderStatus,
    Locale,
    OrdercastMerchant,
    OrdercastProduct,
    OrdercastAttribute,
    OrdercastCategory,
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
)
from .helpers import (
    get_i18n_field_as_dict,
    exists_in_all_ids,
)
from .odoo_repo import OdooRepo, RedisKeys
from .validators import (
    validate_warehouses,
)

logger = structlog.getLogger(__name__)


class OrdercastManager:
    def __init__(self, ordercast_api: OrdercastApi) -> None:
        self.ordercast_api = ordercast_api

    def get_users(self) -> list[OrdercastMerchant]:
        # TODO: handle pagination
        response = self.ordercast_api.get_merchants(request=ListMerchantsRequest())
        users = response.json()["items"]
        return [
            OrdercastMerchant(id=user["id"], name=user["name"], erp_id=user["erp_id"])
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
    ):
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

    def get_billing_addresses(self, merchant_id: int):
        return self.ordercast_api.list_billing_addresses(
            ListBillingAddressesRequest(merchant_id=merchant_id)
        )

    def get_shipping_addresses(self, merchant_id: int):
        return self.ordercast_api.list_shipping_addresses(
            ListShippingAddressesRequest(merchant_id=merchant_id)
        )

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
                OrdercastProduct(id=product["id"], sku=product["sku"])
                for product in result_json["items"]
            ]
        return []

    def get_attributes(self) -> list[OrdercastAttribute]:
        logger.info("Receiving attributes from Ordercast")
        response = self.ordercast_api.get_attributes()
        result_json = response.json()
        return [
            OrdercastAttribute(id=attribute["id"], name=attribute["name"])
            for attribute in result_json
        ]

    def get_categories(self) -> list[OrdercastCategory]:
        logger.info("Receiving categories from Ordercast")
        response = self.ordercast_api.get_categories()
        result_json = response.json()
        return [
            OrdercastCategory(
                id=category["id"], name=category["name"], code=category["code"]
            )
            for category in result_json
        ]

    def get_address(self, address, odoo_repo: OdooRepo):
        if address:
            address_dto = {
                "id": address.id,
                "name": address.name,
                "address_one": address.address_one,
                "postal_code": address.code,
                "phone": address.phone,
                "email": address.email,
            }
            if address.address_two:
                address_dto["address_two"] = address.address_two
            if address.city:
                address_dto["city"] = address.city.name
                if address.city.region:
                    address_dto["region"] = address.city.region.name
            if address.country:
                address_dto["country"] = address.country.name
            if address.copy_from:
                address_id = address.copy_from.id
            else:
                address_id = address.id
            # external_address = AddressExternal.objects.filter(
            #     address_id=address_id
            # ).first()
            external_address = odoo_repo.get(
                key=RedisKeys.ADDRESSES, entity_id=address_id
            )
            if external_address:
                address_dto["_remote_id"] = external_address.odoo_id
            return address_dto

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
        self, product_variants: list[dict[str, Any]], units: list[dict[str, Any]]
    ) -> None:
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
                    price_rates=[],
                    unit_code=product_variant["unit_code"],
                    attribute_values=[
                        {"value_id": a.id} for a in product_variant["attribute_values"]
                    ],
                    place_in_warehouse="",
                    customs_code="",
                    letter="",
                    description=product_variant.get("description", ""),
                )
                for product_variant in product_variants
            ]
        )

    def save_delivery_options(self, delivery_options_dict: dict[str, Any]):
        self.ordercast_api.upsert

        for delivery_option in delivery_options:
            if "name" in delivery_option and delivery_option["name"]:
                name = delivery_option["name"]
                i18n_fields = get_i18n_field_as_dict(delivery_option, "name")
                defaults_data = {"name": name}
                defaults_data.update(i18n_fields)
                defaults_data["code"] = self.get_unique_code(
                    name,
                    "name",
                    DeliveryOption.all_objects.exclude(
                        id=delivery_option["id"]
                    ).order_by("name"),
                    "code",
                    False,
                    symbol_count=3,
                    max_length=16,
                )

                # external_delivery_option = DeliveryOptionExternal.objects.filter(
                #     odoo_id=delivery_option["id"]).first()
                odoo_delivery_option = odoo_repo.get(
                    key=RedisKeys.DELIVERY_OPTIONS, entity_id=delivery_option["id"]
                )
                if odoo_delivery_option:
                    # saved, _ = DeliveryOption.objects.update_or_create(
                    #     id=odoo_delivery_option.delivery_option.id, defaults=defaults_data)
                    # odoo_delivery_option.save()
                    saved = self.ordercast_api.create_delivery_option()
                else:
                    defaults_data["is_removed"] = False
                    # saved, _ = DeliveryOption.all_objects.update_or_create(name=name, defaults=defaults_data)
                    saved = self.ordercast_api.create_delivery_option()

                    existing_odoo_delivery_option = (
                        DeliveryOptionExternal.all_objects.filter(
                            delivery_option_id=saved.id
                        ).first()
                    )
                    if existing_odoo_delivery_option:
                        if not exists_in_all_ids(
                            existing_odoo_delivery_option.odoo_id, delivery_options_dict
                        ):
                            existing_odoo_delivery_option.odoo_id = delivery_option[
                                "id"
                            ]
                            existing_odoo_delivery_option.save()
                        elif (
                            existing_odoo_delivery_option.odoo_id
                            != delivery_option["id"]
                        ):
                            logger.warn(
                                f"There is more than one '{delivery_option['name']}' delivery option {[existing_odoo_delivery_option.odoo_id, delivery_option['id']]} in Odoo, so the first '{existing_odoo_delivery_option.odoo_id}' is used. "
                                f"Please inform Odoo administrators that delivery option names should be unified and stored only in one instance."
                            )
                        existing_odoo_delivery_option.save()
                    else:
                        # DeliveryOptionExternal.objects.update_or_create(delivery_option_id=saved.id,
                        #                                                 odoo_id=delivery_option["id"])
                        odoo_repo.insert(
                            key=RedisKeys.DELIVERY_OPTIONS,
                            entity=OdooDeliveryOption(
                                odoo_id=delivery_option["id"], delivery_option=saved.id
                            ),
                        )

    def save_warehouse(self, warehouses_dict, odoo_repo: OdooRepo):
        warehouses = warehouses_dict["objects"]
        if not warehouses:
            logger.info(f"Deleting warehouses.")
            warehouse_ids = odoo_repo.get_list(RedisKeys.WAREHOUSES)
            # TODO HANDLE
            if warehouse_ids:
                pass
                # warehouses_for_delete = Warehouse.objects.exclude(id__in=warehouse_ids)
                # WarehouseExternal.all_objects.filter(
                #     warehouse_id__in=warehouses_for_delete.values_list('pk', flat=True)).delete()
                # warehouses_for_delete.delete()

        validate_warehouses(warehouses)

        for warehouse in warehouses:
            if "name" in warehouse and warehouse["name"]:
                name = warehouse["name"]
                i18n_fields = get_i18n_field_as_dict(warehouse, "name")
                defaults_data = {"name": name}
                defaults_data.update(i18n_fields)
                # odoo_warehouse = WarehouseExternal.objects.filter(odoo_id=warehouse["id"]).first()
                odoo_warehouse = odoo_repo.get(
                    RedisKeys.WAREHOUSES, entity_id=warehouse["id"]
                )
                if odoo_warehouse:
                    # saved = Warehouse.objects.update_or_create(id=odoo_warehouse.warehouse.id,
                    #                                               defaults=defaults_data)
                    saved = self.ordercast_api.create_warehouse()
                else:
                    defaults_data["is_removed"] = False
                    # saved, _ = Warehouse.all_objects.update_or_create(name=name, defaults=defaults_data)
                    saved = self.ordercast_api.create_warehouse()

                    existing_odoo_warehouse = odoo_repo.get(
                        key=RedisKeys.WAREHOUSES, entity_id=saved.id
                    )

                    if existing_odoo_warehouse:
                        if not exists_in_all_ids(
                            existing_odoo_warehouse.odoo_id, warehouses_dict
                        ):
                            existing_odoo_warehouse.odoo_id = warehouse["id"]
                            existing_odoo_warehouse.save()
                        elif existing_odoo_warehouse.odoo_id != warehouse["id"]:
                            logger.warn(
                                f"There is more than one '{warehouse['name']}' warehouse {[existing_odoo_warehouse.odoo_id, warehouse['id']]} in Odoo, so the first '{existing_odoo_warehouse.odoo_id}' is used. "
                                f"Please inform Odoo administrators that warehouse names should be unified and stored only in one instance."
                            )
                        existing_odoo_warehouse.save()
                    else:
                        odoo_repo.insert(
                            key=RedisKeys.WAREHOUSES,
                            entity=OdooWarehouse(
                                odoo_id=warehouse["id"], warehouse_id=saved.id
                            ),
                        )
                warehouse["saved_id"] = saved.id
                warehouse["saved"] = saved

    def get_orders(self, order_ids, odoo_repo: OdooRepo, from_date=None):
        orders = self.ordercast_api.get_orders(order_ids, from_date)

        result = []
        for order in orders:
            order_dto = {
                "id": order.id,
                "name": f"OC{str(order.id).zfill(5)}",
                "status": order.status,
            }
            billing_address_dto = self.get_address(
                order.billing_info.address, odoo_repo=odoo_repo
            )
            shipping_address_dto = self.get_address(order.address, odoo_repo=odoo_repo)
            if shipping_address_dto:
                order_dto["shipping_address"] = shipping_address_dto
            if billing_address_dto:
                billing_address_dto["name"] = order.billing_info.enterprise_name
                billing_address_dto["vat"] = order.billing_info.vat
                order_dto["billing_address"] = billing_address_dto
            if order.delivery_option:
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
            if order.warehouse:
                warehouse = order.warehouse
                warehouse_dto = {"id": warehouse.id, "name": warehouse.name}
                odoo_warehouse = odoo_repo.get(
                    key=RedisKeys.WAREHOUSES, entity_id=warehouse.id
                )
                if odoo_warehouse:
                    warehouse_dto["_remote_id"] = odoo_warehouse.odoo_id
                else:
                    logger.info(
                        f"The warehouse name '{warehouse.name}' has no remote id. Please sync it first with Odoo."
                    )
                order_dto["warehouse"] = warehouse_dto

            odoo_order = odoo_repo.get(key=RedisKeys.ORDERS, entity_id=order.id)
            if odoo_order:
                order_dto["_remote_id"] = odoo_order.odoo_id
            odoo_user = odoo_repo.get(key=RedisKeys.USERS, entity_id=order.user)
            if odoo_user:
                order_dto["user_remote_id"] = odoo_user.odoo_id
            if order.invoice_number:
                order_dto["invoice_number"] = order.invoice_number
            if order.note:
                order_dto["note"] = order.note
            if order.basket:
                basket = order.basket
                basket_dto = {
                    "id": basket.id,
                    "total": basket.total,
                    "grand_total": basket.grand_total,
                    "total_taxes": basket.total_taxes,
                    "vat_percent": basket.vat_percent,
                }
                order_dto["basket"] = basket_dto
                if basket.basket_products:
                    basket_products = []
                    basket_dto["basket_products"] = basket_products
                    for basket_product in basket.basket_products.all():
                        basket_product_dto = {
                            "id": basket_product.id,
                            "price": basket_product.price,
                            "quantity": basket_product.quantity,
                            "total_price": basket_product.total,
                            "total_quantity": basket_product.total_quantity,
                        }
                        if basket_product.final_quantity:
                            basket_product_dto[
                                "final_quantity"
                            ] = basket_product.final_quantity

                        if basket_product.product:
                            product = basket_product.product
                            product_dto = {
                                "id": product.id,
                                "ref": product.ref,
                                "name": product.name,
                            }
                            odoo_product = odoo_repo.get(
                                key=RedisKeys.PRODUCT_VARIANTS, entity_id=product.id
                            )
                            if odoo_product:
                                product_dto["_remote_id"] = odoo_product.odoo_id
                            basket_product_dto["product"] = product_dto
                        odoo_basket_product = odoo_repo.get(
                            key=RedisKeys.BASKET_PRODUCT, entity_id=basket_product.id
                        )
                        if odoo_basket_product:
                            basket_product_dto[
                                "_remote_id"
                            ] = odoo_basket_product.odoo_id
                        basket_products.append(basket_product_dto)
            result.append(order_dto)

        return result

    def sync_orders(self, orders, odoo_repo: OdooRepo) -> None:
        for order in orders:
            odoo_order = odoo_repo.get(key=RedisKeys.ORDERS, entity_id=order["id"])
            if odoo_order:
                odoo_order.odoo_order_status = order["status"]
                odoo_order.odoo_invoice_status = order["invoice_status"]

                # todo: add logic of updating products amount, out of stock it should be investigated.

                existing_order = odoo_order.order
                if "invoice_file_data" in order:
                    # self.save_file(order['invoice_file_name'], order['invoice_file_data'], existing_order.invoice)
                    logger.info(
                        f"Invoice file {order['invoice_file_name']} added for order {existing_order.id}."
                    )
                elif existing_order.invoice:
                    logger.info(
                        f"Invoice file {existing_order.invoice.url.split('/')[-1] if existing_order.invoice and existing_order.invoice.url else ''} removed from order {existing_order.id}."
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
                    f"Address with remote_id={order['id']} not exists in the system, please run sync task first."
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
                    f"Order '{order['name']}' has Odoo oder status: '{external_order.odoo_order_status}' and invoice status: '{external_order.odoo_invoice_status}', updating to 'Processed'."
                )
                if existing_order.invoice:
                    url = utils.get_invoice_full_url(existing_order.invoice)
                    existing_order.processed(url)
                else:
                    logger.warn(
                        f"Order '{order['name']}' has no invoice file, so changing status to 'Processed' ignored."
                    )
            elif (
                external_order.odoo_order_status == OrderStatus.DONE_STATUS
                and existing_order.status != OrderStatus.COMPLETED_STATUS
            ):
                logger.info(
                    f"Order '{order['name']}' has Odoo oder status: '{external_order.odoo_order_status}' and invoice status: '{external_order.odoo_invoice_status}', updating to 'Completed'."
                )
                existing_order.complete()
            elif (
                external_order.odoo_order_status == OrderStatus.CANCEL_STATUS
                and existing_order.status != OrderStatus.CANCELLED_BY_ADMIN_STATUS
            ):
                logger.info(
                    f"Order '{order['name']}' has Odoo oder status: '{external_order.odoo_order_status}' and invoice status: '{external_order.odoo_invoice_status}', updating to 'Cancelled'."
                )
                if existing_order.status in [
                    OrderStatus.SUBMITTED_STATUS,
                    OrderStatus.IN_PROGRESS_STATUS,
                ]:
                    existing_order.cancel(
                        existing_order.operator
                    )  # todo: add original operator or admin from local user list. it is imposible now to find out the original canceller user
                else:
                    logger.warn(
                        f"Order '{order['name']}' can not be cancelled, since it has '{existing_order.status}' status and only orders with '{OrderStatus.SUBMITTED_STATUS}' or '{OrderStatus.IN_PROGRESS_STATUS}' statuses permitted to cancel."
                    )
            existing_order.save()
        except Exception as exc:
            logger.error(f"Error during updating order status locally.")
            raise exc


# @lru_cache()
def get_ordercast_manager(
    ordercast_api: Annotated[OrdercastApi, Depends(get_ordercast_api)]
) -> OrdercastManager:
    return OrdercastManager(ordercast_api)
