from datetime import datetime, timezone
from typing import Annotated, Any

import structlog
from fastapi import Depends

from src.api import (
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
)
from src.data import (
    OdooProductVariant,
    OdooDeliveryOption,
    OdooWarehouse,
    OdooOrder,
    InvoiceStatus,
    OrderStatus,
    Locale,
    OrdercastMerchant,
)
from src.infrastructure import OrdercastApi, get_ordercast_api
from .exceptions import OdooSyncException
from .helpers import (
    is_length_not_in_range,
    get_i18n_field_as_dict,
    exists_in_all_ids,
    str_to_int,
)
from .odoo_repo import OdooRepo, RedisKeys
from .validators import (
    validate_delivery_options,
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
                    parent_id=category["parent"],
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
        categories: dict[str, Any],
        products: dict[str, Any],
        attributes: dict[str, Any],
        product_variants: dict[str, Any],
    ) -> None:
        categories = categories["objects"]
        products = products["objects"]
        product_variants = product_variants["objects"]
        attributes = attributes["objects"]
        product_variants = sorted(product_variants, key=lambda d: d["display_name"])

        saved_product_variants_ids = []
        for product_variant in product_variants:
            remote_id = product_variant["id"]

            i18n_fields = get_i18n_field_as_dict(
                product_variant, "display_name", "name", r"^\[.*] ?"
            )

            name = product_variant["display_name"]
            ref = product_variant["code"]
            price = None
            if "price" in product_variant:
                price = product_variant["price"]
            pack = 1
            if "unit_count" in product_variant:
                pack = product_variant["unit_count"]
            unit_name = None
            if "attr_unit" in product_variant:
                unit_name = product_variant["attr_unit"]

            barcode = ""
            if "barcode" in product_variant:
                barcode = product_variant["barcode"]
                if is_length_not_in_range(barcode, 1, 24):
                    raise OdooSyncException(
                        f"Received product barcode '{barcode}' has more than max 24 symbols. Please correct it in Odoo."
                    )

            unit = None
            if unit_name:
                # unit, is_new = Unit.objects.update_or_create(name=unit_name.upper(), hint=unit_name)
                unit = self.ordercast_api.upsert_units()

            group = None
            if (
                products
                and "group" in product_variant
                and product_variant["group"]
                and len(product_variant["group"]) > 0
            ):
                group_id = product_variant["group"][0]
                for saved_groups in products:
                    if saved_groups["id"] == group_id:
                        group = saved_groups["saved"]
                        break

            defaults = {
                "name": name,
                "pack": pack,
                "group": group,
                "unit": unit,
                "barcode": barcode,
            }
            defaults.update(i18n_fields)
            defaults["is_removed"] = False

            # odoo_product = ProductExternal.objects.filter(odoo_id=remote_id).first()
            odoo_product = odoo_repo.get(
                key=RedisKeys.PRODUCT_VARIANTS, entity_id=remote_id
            )
            if odoo_product:
                defaults["ref"] = ref
                # saved_product, _ = Product.all_objects.update_or_create(id=odoo_product.product.id,
                #                                                         defaults=defaults)
                saved_product = self.ordercast_api.upsert_products(
                    id=odoo_product.product.id, defaults=defaults
                )
            else:
                # saved_product = Product.all_objects.update_or_create(ref=ref, defaults=defaults)
                saved_product = self.ordercast_api.upsert_products(
                    ref=ref, defaults=defaults
                )
                # existing_odoo_product = ProductExternal.objects.filter(product__id=saved_product.id).first()
                existing_odoo_product = odoo_repo.get(
                    key=RedisKeys.PRODUCT_VARIANTS, entity_id=saved_product.id
                )

                if existing_odoo_product:
                    if not exists_in_all_ids(
                        existing_odoo_product.odoo_id, product_variants
                    ):
                        existing_odoo_product.odoo_id = remote_id
                        existing_odoo_product.save()
                    elif existing_odoo_product.odoo_id != remote_id:
                        logger.warn(
                            f"There is more than one '{name}' product {[existing_odoo_product.odoo_id, remote_id]} in Odoo, so the first '{existing_odoo_product.odoo_id}'is used. "
                            f"Please inform Odoo administrators that products should be unified and stored only in one instance."
                        )
                        existing_odoo_product.save()
                    # self.remove_duplicate_object_id(remote_id, products_dict)
                else:
                    # ProductExternal.objects.update_or_create(product_id=saved_product.id, odoo_id=remote_id)
                    odoo_repo.insert(
                        key=RedisKeys.PRODUCT_VARIANTS,
                        entity=OdooProductVariant(
                            odoo_id=remote_id, product=saved_product.id
                        ),
                    )

            # clear current categories and attributes.
            saved_product.category_products.all().delete()
            saved_product.attributes.all().delete()

            product_variant["saved_id"] = saved_product.id
            product_variant["saved"] = saved_product

            if (
                categories
                and "category" in product_variant
                and product_variant["category"]
                and len(product_variant["category"]) > 0
            ):
                product_categories = product_variant["category"]
                saved_product.categories = None
                if isinstance(product_categories, list):
                    for product_category in product_categories:
                        for category in categories:
                            if category["id"] == product_category:
                                saved_category = category["saved"]
                                saved_category.products.add(saved_product)
                                saved_category.save()
                                if saved_product.categories is None:
                                    saved_product.categories = []
                                if saved_category.code not in saved_product.categories:
                                    saved_product.categories.append(saved_category.code)
                                    saved_product.save()
                                break
            if (
                attributes
                and "attribute_values" in product_variant
                and len(product_variant["attribute_values"]) > 0
            ):
                product_attribute_values = product_variant["attribute_values"]
                for product_attribute_value in product_attribute_values:
                    found = False
                    for attribute in attributes:
                        if "values" in attribute:
                            for attribute_value in attribute["values"]:
                                if (
                                    "id" in attribute_value
                                    and product_attribute_value == attribute_value["id"]
                                ):
                                    if (
                                        "saved" in attribute
                                        and "saved" in attribute_value
                                    ):
                                        (
                                            saved_product_attribute,
                                            is_new,
                                        ) = ProductAttribute.objects.update_or_create(
                                            product=product_variant["saved"],
                                            category=attribute["saved"],
                                            attribute=attribute_value["saved"],
                                        )
                                        if (
                                            "saved_product_attribute_ids"
                                            not in product_variant
                                        ):
                                            product_variant[
                                                "saved_product_attribute_ids"
                                            ] = []
                                        if (
                                            "saved_product_attributes"
                                            not in product_variant
                                        ):
                                            product_variant[
                                                "saved_product_attributes"
                                            ] = []

                                        product_variant[
                                            "saved_product_attribute_ids"
                                        ].append(saved_product_attribute.id)
                                        product_variant[
                                            "saved_product_attributes"
                                        ].append(saved_product_attribute)

                                        # if saved_product:
                                        #     if saved_product.attributes is None:
                                        #         saved_product.attributes = []
                                        #     if saved_product_attribute.id not in saved_product.attributes:
                                        #         saved_product.attributes.append(saved_product_attribute)
                                        #         saved_product.save()
                                        found = True
                                        break
                                    else:
                                        logger.error(
                                            f"Attribute {attribute['name']} or value {attribute_value['name']} is not saved."
                                        )
                        if found:
                            break

            if "image" in product_variant:
                self.save_image(
                    saved_product.pk, product_variant["image"], saved_product.image
                )
            elif saved_product.image:
                self.delete_file(saved_product.image)

            saved_product.update_search_vector()
            product_variant["saved"] = saved_product
            saved_product_variants_ids.append(saved_product.id)
            counter = 0
            price_discounts = product_variant["price_discounts"]
            if price_discounts:
                price_discounts = price_discounts.split(";")

            def get_discount():
                result = price_discounts
                if isinstance(price_discounts, list):
                    if len(price_discounts) >= counter + 1:
                        result = price_discounts[counter]
                    else:
                        result = 0
                return str_to_int(result, 0)

            def get_discounted_price():
                discount = get_discount()
                result = price - price * discount / 100
                return result

            # TODO: price_rate
            for tariff in TariffGroup.objects.all().order_by("name"):
                discounted_price = get_discounted_price()
                price_saved, price_is_new = ProductPrice.objects.update_or_create(
                    product=saved_product,
                    tariff=tariff,
                    defaults={"price": discounted_price},
                )
                counter += 1

        # set grouper field for the products
        if saved_product_variants_ids:
            grouper_attributes = [
                (a.group.id, [b.category.code for b in a.attributes.all()])
                for a in Product.objects.filter(
                    id__in=saved_product_variants_ids,
                    attributes__gt=1,
                    group__isnull=False,
                )
                .distinct("group")
                .order_by("group")
            ]
            if grouper_attributes:
                for grouper in grouper_attributes:
                    if len(grouper) > 1:
                        ProductGroup.objects.filter(id=grouper[0]).update(
                            grouper=grouper[1]
                        )

        logger.info(f"Deleting unused objects.")

        def hard_delete_category_external(obj_id):
            CategoryExternal.all_objects.filter(category_id=obj_id).delete()

        def delete_attributes(actual_attributes):
            attributes_for_delete = Attribute.objects.exclude(
                id__in=actual_attributes
            ).filter(productattribute__isnull=True)
            AttributeExternal.all_objects.filter(
                attribute_id__in=attributes_for_delete.values_list("pk", flat=True)
            ).delete()
            attributes_for_delete.delete()

        category_ids = self.get_existing_ids(
            categories,
            CategoryExternal.objects.filter(category_type=Category.CLASS_TYPE),
            "category_id",
        )
        catalogs_ids = self.get_existing_ids(
            categories,
            CategoryExternal.objects.filter(category_type=Category.CATALOG_TYPE),
            "category_id",
        )
        group_ids = self.get_existing_ids(
            products, ProductGroupExternal.objects.all(), "product_group_id"
        )
        product_ids = self.get_existing_ids(
            product_variants, ProductExternal.objects.all(), "product_id"
        )
        attribute_ids = self.get_existing_ids(
            attributes,
            CategoryExternal.objects.filter(
                category_type=Category.PRODUCT_ATTRIBUTE_TYPE
            ),
            "category_id",
        )
        attribute_value_ids = self.get_existing_ids(
            attributes["attribute_values"],
            AttributeExternal.objects.all(),
            "attribute_id",
        )

        parse_products.delete_products(
            group_ids, product_ids
        )  # todo: move this logic to common manager
        parse_products.delete_categories_by_ids(
            Category.CLASS_TYPE, category_ids, hard_delete_category_external, False
        )
        parse_products.delete_categories_by_ids(
            Category.CATALOG_TYPE, catalogs_ids, hard_delete_category_external, False
        )
        parse_products.delete_categories_by_ids(
            Category.PRODUCT_ATTRIBUTE_TYPE,
            attribute_ids,
            hard_delete_category_external,
            False,
        )
        delete_attributes(attribute_value_ids)

    def save_delivery_option(
        self, delivery_options_dict: dict[str, Any], odoo_repo: OdooRepo
    ):
        delivery_options = delivery_options_dict["objects"]
        if not delivery_options:
            logger.info(f"Deleting delivery options.")
            delivery_option_ids = odoo_repo.get_list(key=RedisKeys.DELIVERY_OPTIONS)

            # TODO: HANDLE
            if delivery_option_ids:
                pass
            #     delivery_option_for_delete = DeliveryOption.objects.exclude(id__in=delivery_option_ids)
            #     DeliveryOptionExternal.all_objects.filter(
            #         delivery_option_id__in=delivery_option_for_delete.values_list('pk', flat=True)).delete()
            #     delivery_option_for_delete.delete()
            return

        validate_delivery_options(delivery_options)

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
                delivery_option["saved_id"] = saved.id
                delivery_option["saved"] = saved

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
