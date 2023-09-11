from datetime import datetime, timezone
from typing import Annotated, Any, Optional

import structlog
from fastapi import Depends

from src.api import (
    CreateShippingAddressRequest,
    ListBillingAddressesRequest,
    ListShippingAddressesRequest,
    CreateOrderRequest,
)
from src.data import (
    OdooProductGroup,
    OdooAttribute,
    OdooProduct,
    OdooDeliveryOption,
    OdooWarehouse,
    OdooOrder,
    InvoiceStatus,
    OrderStatus,
)
from src.infrastructure import OrdercastApi, get_ordercast_api
from .exceptions import OdooSyncException
from .helpers import (
    is_not_empty,
    is_empty,
    is_length_not_in_range,
    get_i18n_field_as_dict,
    is_not_ref,
    exists_in_all_ids,
    str_to_int,
)
from .odoo_repo import OdooRepo, RedisKeys
from .validators import (
    validate_product_groups,
    validate_categories,
    validate_products,
    validate_attributes,
    validate_delivery_options,
    validate_warehouses,
)

logger = structlog.getLogger(__name__)


class OrdercastManager:
    def __init__(self, ordercast_api: OrdercastApi) -> None:
        self.ordercast_api = ordercast_api

    def get_user(self, email: str):
        return self.ordercast_api.get_merchant(email)

    def upsert_user(self, email: str, defaults: dict[str, Any]):
        return self.ordercast_api.bulk_signup()

    def create_shipping_address(
        self,
        user_id: int,
        name: str,
        street: str,
        city: str,
        postcode: str,
        country: str,
        contact_name: Optional[str] = None,
        contact_phone: Optional[str] = None,
    ):
        return self.ordercast_api.create_shipping_address(
            CreateShippingAddressRequest(
                merchange_id=user_id,
                name=name,
                street=street,
                city=city,
                postcode=postcode,
                country=country,
                contact_name=contact_name,
                contact_phone=contact_phone,
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

    def get_users(self, odoo_repo: OdooRepo):
        # users = User.objects.all()
        users = self.ordercast_api.get_all_merchants()
        users_to_create = []
        for user in users:
            user_dto = {"id": user.id, "name": user.name}

            # user_remote = UserExternal.objects.filter(user_id=user.id).first()
            user_remote = odoo_repo.get(key=RedisKeys.USERS, entity_id=user.id)
            if user_remote:
                user_dto["_remote_id"] = user_remote.odoo_id
            # if user.erp_id:
            #     user_dto["erp_id"] = user.erp_id
            if user.profile:
                user_dto["language"] = user.profile.language
                if user.profile.website:
                    user_dto["website"] = user.profile.website
                if user.profile.signup_info:
                    user_dto["comment"] = user.profile.signup_info

            user_dto["name"] = user.name
            user_dto["email"] = user.email
            # user_dto['approved'] = user.is_approved
            # user_dto['activated'] = user.is_active
            # billing_addresses = Billing.objects.filter(user_id=user.id).all()
            billing_addresses = self.get_billing_addresses(user.id)
            billing_address_dtos = []
            if billing_addresses and billing_addresses.count() > 0:
                for billing_address in billing_addresses:
                    if billing_address.billing_info:
                        billing_address_dto = self.get_address(
                            billing_address.billing_info.address
                        )
                        billing_address_dto[
                            "name"
                        ] = billing_address.billing_info.enterprise_name
                        billing_address_dto["vat"] = billing_address.billing_info.vat
                        if is_not_empty(user_dto, "website"):
                            billing_address_dto["website"] = user_dto["website"]
                        # if is_not_empty(user_dto, 'email'):
                        #     billing_address_dto['email'] = user_dto['email']
                        if is_not_empty(user_dto, "language"):
                            billing_address_dto["language"] = user_dto["language"]
                        if is_not_empty(user_dto, "signup_info"):
                            billing_address_dto["comment"] = user_dto["signup_info"]
                        if is_not_empty(user_dto, "_remote_id"):
                            if (
                                is_empty(billing_address_dto, "_remote_id")
                                or billing_address_dto["_remote_id"]
                                != user_dto["_remote_id"]
                            ):
                                billing_address_dto["parent_id"] = user_dto[
                                    "_remote_id"
                                ]
                        billing_address_dtos.append(billing_address_dto)

                user_dto["billing_addresses"] = billing_address_dtos

            # shipping_addresses = ShippingAddress.objects.filter(user_id=user.id).all()
            shipping_addresses = self.get_shipping_addresses(user.id)
            shipping_address_dtos = []
            if shipping_addresses and shipping_addresses.count() > 0:
                for shipping_address in shipping_addresses:
                    if shipping_address.address:
                        shipping_address_dto = self.get_address(
                            shipping_address.address, odoo_repo=odoo_repo
                        )
                        # shipping_address_dto['name'] = shipping_address.name
                        if is_not_empty(user_dto, "website"):
                            shipping_address_dto["website"] = user_dto["website"]
                        # shipping_address_dto['email'] = user_dto['email']
                        if is_not_empty(user_dto, "language"):
                            shipping_address_dto["language"] = user_dto["language"]
                        if is_not_empty(user_dto, "signup_info"):
                            shipping_address_dto["comment"] = user_dto["signup_info"]
                        if is_not_empty(user_dto, "_remote_id"):
                            if (
                                is_empty(shipping_address_dto, "_remote_id")
                                or shipping_address_dto["_remote_id"]
                                != user_dto["_remote_id"]
                            ):
                                shipping_address_dto["parent_id"] = user_dto[
                                    "_remote_id"
                                ]

                        shipping_address_dtos.append(shipping_address_dto)

                user_dto["shipping_addresses"] = shipping_address_dtos
            users_to_create.append(user_dto)

        return users_to_create

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

    def save_product_groups(self, product_groups, odoo_repo: OdooRepo):
        groups = product_groups["objects"]
        validate_product_groups(groups)

        for group in groups:
            name = group["name"]
            defaults = {"name": name}

            i18n_fields = get_i18n_field_as_dict(group, "name")
            defaults.update(i18n_fields)

            if "ref" in group and len(group["ref"].strip()) > 1:
                ref = group["ref"]  # fixme: add this hard validation, after testing
                # ref = self.get_unique_code(group['name'], 'name', ProductGroup.objects.order_by("name"), 'ref', False)
            else:
                ref = self.get_unique_code(
                    group["name"],
                    "name",
                    ProductGroup.all_objects.exclude(id=group["id"]).order_by("name"),
                    "ref",
                    False,
                )
            if is_length_not_in_range(ref, 1, 191):
                raise OdooSyncException(
                    f"Received group '{ref}' has more than max 40 symbols. Please correct it in Odoo."
                )
            if is_not_ref(ref):
                raise OdooSyncException(
                    f"Received group '{ref}' should contain only alpha, numbers, hyphen and dot. Please correct it in Odoo."
                )

            # external_group = ProductGroupExternal.objects.filter(
            #     odoo_id=group["id"]
            # ).first()
            odoo_product_group = odoo_repo.get(
                key=RedisKeys.PRODUCT_GROUPS, entity_id=group["id"]
            )
            defaults["is_removed"] = False
            if odoo_product_group:
                defaults["ref"] = ref
                # saved, _ = ProductGroup.all_objects.update_or_create(
                #     id=odoo_product_group.product_group.id, defaults=defaults
                # )
                saved = self.ordercast_api.create_product_group(
                    id=odoo_product_group.product_group.id, defaults=defaults
                )
            else:
                # saved, _ = ProductGroup.all_objects.update_or_create(
                #     ref=ref, defaults=defaults
                # )
                saved = self.ordercast_api.create_product_group(
                    ref=ref, defaults=defaults
                )
                # existing_odoo_product_group = ProductGroupExternal.objects.filter(
                #     product_group=saved
                # ).first()
                existing_odoo_product_group = odoo_repo.get(
                    key=RedisKeys.PRODUCT_GROUPS, entity_id=saved.id
                )
                if existing_odoo_product_group:
                    if not exists_in_all_ids(
                        existing_odoo_product_group.odoo_id, product_groups
                    ):
                        existing_odoo_product_group.odoo_id = group["id"]
                        existing_odoo_product_group.save()
                    elif existing_odoo_product_group.odoo_id != group["id"]:
                        logger.warn(
                            f"There is more than one '{group['name']}' group {[existing_odoo_product_group.odoo_id, group['id']]} in Odoo, so the first '{existing_odoo_product_group.odoo_id}' is used. "
                            f"Please inform Odoo administrators that groups (product.templates) should be unified and stored only in one instance."
                        )
                        existing_odoo_product_group.save()
                        # self.remove_duplicate_object_id(group['id'], groups_dict)
                else:
                    # ProductGroupExternal.objects.update_or_create(
                    #     product_group_id=saved.id, odoo_id=group["id"]
                    # )
                    odoo_repo.insert(
                        key=RedisKeys.PRODUCT_GROUPS,
                        entity=OdooProductGroup(
                            odoo_id=group["id"], product_group=saved.id
                        ),
                    )

            # TODO: do we need it?
            # if "image" in group:
            #     self.save_image(saved.pk, group["image"], saved.image)
            # elif saved.image:
            #     self.delete_file(saved.image)

            saved.update_search_vector()

            group["saved_id"] = saved.id
            group["saved"] = saved

    def save_categories(self, categories_dict: dict[str, Any]) -> None:
        categories = categories_dict["objects"]

        if not categories:
            return

        categories = sorted(categories, key=lambda d: d["name"])
        validate_categories(categories)

        # TODO: check
        for category in categories:  # set parent category
            if "parent" in category and category["parent"] and "saved" in category:
                for parent in categories:
                    if parent["id"] in category["parent"]:
                        saved_child = category["saved"]
                        saved_child.parent = parent["saved"]
                        saved_child.save()

        # TODO: do we need it?
        # for category in categories:  # set paths
        #     if 'saved' in category:
        #         Category.objects.set_path_defaults(category['saved'])

        self.ordercast_api.upsert_categories(categories)

    def save_attributes(self, attributes: dict[str, Any], odoo_repo: OdooRepo) -> None:
        attributes = attributes["objects"]

        if not attributes:
            return

        validate_attributes(attributes)

        for attribute in attributes:  # save locally received attributes
            self.upsert_user(attribute, attributes, Category.PRODUCT_ATTRIBUTE_TYPE)

            if "values" in attribute:
                for value in attribute["values"]:
                    if "id" in value and "name" in value:
                        defaults_data = {}
                        if "position" in value:
                            defaults_data["position"] = value["position"]

                            i18n_fields = get_i18n_field_as_dict(value, "name")
                            defaults_data.update(i18n_fields)
                            # external_attribute_value = AttributeExternal.objects.filter(odoo_id=value["id"]).first()
                            external_attribute_value = odoo_repo.get(
                                keys=RedisKeys.ATTRIBUTES, entity_id=value["id"]
                            )
                            if external_attribute_value:
                                defaults_data["name"] = value["name"]
                                # saved, _ = Attribute.objects.update_or_create(
                                #     id=external_attribute_value.attribute.id, defaults=defaults_data)
                                saved = self.ordercast_api.upsert_attributes(
                                    id=external_attribute_value.attribute.id,
                                    defaults=defaults_data,
                                )
                            else:
                                # saved, _ = Attribute.objects.update_or_create(name=value['name'],
                                #                                               defaults=defaults_data)
                                saved = self.ordercast_api.upsert_attributes(
                                    name=value["name"], defaults=defaults_data
                                )

                                # existing_external_object = AttributeExternal.objects.filter(
                                #     attribute_id=saved.id).first()
                                existing_odoo_attribute = odoo_repo.get(
                                    key=RedisKeys.ATTRIBUTES, entity_id=saved.id
                                )
                                if existing_odoo_attribute:
                                    if not exists_in_all_ids(
                                        existing_odoo_attribute.odoo_id,
                                        attributes["attribute_values"],
                                    ):
                                        existing_odoo_attribute.odoo_id = value["id"]
                                        existing_odoo_attribute.save()
                                    elif existing_odoo_attribute.odoo_id != value["id"]:
                                        logger.warn(
                                            f"There is more than one '{value['name']}' attribute value {[existing_odoo_attribute.odoo_id, value['id']]} in Odoo, so the first '{existing_odoo_attribute.odoo_id}' is used. "
                                            f"Please inform Odoo administrators that attribute values should be unified and stored only in one instance."
                                        )
                                    existing_odoo_attribute.save()
                                else:
                                    # AttributeExternal.objects.update_or_create(attribute_id=saved.id,
                                    #                                            odoo_id=value["id"])
                                    odoo_repo.insert(
                                        key=RedisKeys.ATTRIBUTES,
                                        entity=OdooAttribute(
                                            odoo_id=value["id"], attribute=saved.id
                                        ),
                                    )
                            value["saved_id"] = saved.id
                            value["saved"] = saved

    def save_products(
        self, categories, product_groups, attributes, products, odoo_repo: OdooRepo
    ) -> None:
        categories = categories["objects"]
        groups = product_groups["objects"]
        products = products["objects"]
        attributes = attributes["objects"]
        products = sorted(products, key=lambda d: d["display_name"])

        validate_products(products)

        saved_product_ids = []
        for product in products:
            remote_id = product["id"]

            i18n_fields = get_i18n_field_as_dict(
                product, "display_name", "name", r"^\[.*] ?"
            )

            name = product["display_name"]
            ref = product["code"]
            price = None
            if "price" in product:
                price = product["price"]
            pack = 1
            if "unit_count" in product:
                pack = product["unit_count"]
            unit_name = None
            if "attr_unit" in product:
                unit_name = product["attr_unit"]

            barcode = ""
            if "barcode" in product:
                barcode = product["barcode"]
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
                groups
                and "group" in product
                and product["group"]
                and len(product["group"]) > 0
            ):
                group_id = product["group"][0]
                for saved_groups in groups:
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
            odoo_product = odoo_repo.get(key=RedisKeys.PRODUCTS, entity_id=remote_id)
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
                    key=RedisKeys.PRODUCTS, entity_id=saved_product.id
                )

                if existing_odoo_product:
                    if not exists_in_all_ids(existing_odoo_product.odoo_id, products):
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
                        key=RedisKeys.PRODUCTS,
                        entity=OdooProduct(odoo_id=remote_id, product=saved_product.id),
                    )

            # clear current categories and attributes.
            saved_product.category_products.all().delete()
            saved_product.attributes.all().delete()

            product["saved_id"] = saved_product.id
            product["saved"] = saved_product

            if (
                categories
                and "category" in product
                and product["category"]
                and len(product["category"]) > 0
            ):
                product_categories = product["category"]
                saved_product.categories = None
                if type(product_categories) == list:
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
                and "attribute_values" in product
                and len(product["attribute_values"]) > 0
            ):
                product_attribute_values = product["attribute_values"]
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
                                            product=product["saved"],
                                            category=attribute["saved"],
                                            attribute=attribute_value["saved"],
                                        )
                                        if "saved_product_attribute_ids" not in product:
                                            product["saved_product_attribute_ids"] = []
                                        if "saved_product_attributes" not in product:
                                            product["saved_product_attributes"] = []

                                        product["saved_product_attribute_ids"].append(
                                            saved_product_attribute.id
                                        )
                                        product["saved_product_attributes"].append(
                                            saved_product_attribute
                                        )

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

            if "image" in product:
                self.save_image(saved_product.pk, product["image"], saved_product.image)
            elif saved_product.image:
                self.delete_file(saved_product.image)

            saved_product.update_search_vector()
            product["saved"] = saved_product
            saved_product_ids.append(saved_product.id)
            counter = 0
            price_discounts = product["price_discounts"]
            if price_discounts:
                price_discounts = price_discounts.split(";")

            def get_discount():
                result = price_discounts
                if type(price_discounts) == list:
                    if len(price_discounts) >= counter + 1:
                        result = price_discounts[counter]
                    else:
                        result = 0
                return str_to_int(result, 0)

            def get_discounted_price():
                discount = get_discount()
                result = price - price * discount / 100
                return result

            for tariff in TariffGroup.objects.all().order_by("name"):
                discounted_price = get_discounted_price()
                price_saved, price_is_new = ProductPrice.objects.update_or_create(
                    product=saved_product,
                    tariff=tariff,
                    defaults={"price": discounted_price},
                )
                counter += 1

        # set grouper field for the products
        if saved_product_ids:
            grouper_attributes = [
                (a.group.id, [b.category.code for b in a.attributes.all()])
                for a in Product.objects.filter(
                    id__in=saved_product_ids, attributes__gt=1, group__isnull=False
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
            product_groups, ProductGroupExternal.objects.all(), "product_group_id"
        )
        product_ids = self.get_existing_ids(
            products, ProductExternal.objects.all(), "product_id"
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
                                key=RedisKeys.PRODUCTS, entity_id=product.id
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
