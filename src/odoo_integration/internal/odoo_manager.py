from datetime import datetime, timezone
from typing import Annotated, Optional, Any

import structlog
from fastapi import Depends
from odoo_rpc_client.connection.jsonrpc import JSONRPCError

from src.data import (
    OdooUser,
    OdooAddress,
    PartnerType,
    PartnerAddressType,
    OrderStatus,
    OdooOrder,
    OdooBasketProduct,
)
from src.infrastructure import OdooClient, get_odoo_client
from .exceptions import OdooSyncException
from .helpers import (
    is_empty,
    is_not_empty,
    get_i18n_field_as_dict,
    check_remote_id,
    get_entity_name_as_i18n,
)
from .odoo_repo import OdooRepo, get_odoo_repo, RedisKeys
from .partner import Partner

logger = structlog.getLogger(__name__)


class OdooManager:
    def __init__(self, client: OdooClient, repo: OdooRepo):
        self._client = client
        self._repo = repo

    def receive_partner_users(self, exclude_user_ids=None):
        users = self.receive_partners(
            exclude_user_ids=exclude_user_ids, partner_type=PartnerType.USER
        )

        if not users:
            return []

        result = []
        addresses = self.receive_partners(
            parent_ids=[u["id"] for u in users], partner_type=PartnerType.ADDRESS
        )
        user_id_to_billing_addresses = {
            user["id"]: [
                address
                for address in addresses
                if address["parent_id"] == user["id"]
                and address["type"] == PartnerAddressType.INVOICE.value
            ]
            for user in users
        }
        user_id_to_shipping_addresses = {
            user["id"]: [
                address
                for address in addresses
                if address["parent_id"] == user["id"]
                and address["type"] == PartnerAddressType.DELIVERY.value
            ]
            for user in users
        }
        for user in users:
            user["billing_addresses"] = user_id_to_billing_addresses.get(user["id"], [])
            user["shipping_addresses"] = user_id_to_shipping_addresses.get(
                user["id"], []
            )
            result.append(user)

        return result

    def receive_partners(
        self, exclude_user_ids=None, parent_ids=None, partner_type=None
    ):
        api_filter_criteria = [
            ("is_company", "=", False),
            ("active", "in", [True, False]),
        ]
        if exclude_user_ids:
            api_filter_criteria.append(("id", "not in", exclude_user_ids))
        if parent_ids:
            api_filter_criteria.append(("parent_id", "in", parent_ids))
        if partner_type:
            if partner_type == PartnerType.USER:
                api_filter_criteria.extend(
                    [
                        ("name", "!=", False),
                        ("email", "!=", False),
                        ("parent_id", "=", False),
                    ]
                )
            elif partner_type == PartnerType.ADDRESS:
                api_filter_criteria.extend(
                    [
                        ("name", "!=", False),
                        ("parent_id", "!=", False),
                        (
                            "type",
                            "in",
                            [
                                PartnerAddressType.INVOICE.value,
                                PartnerAddressType.DELIVERY.value,
                            ],
                        ),
                    ]
                )

        partners = self._client.get_objects("res.partner", criteria=api_filter_criteria)
        remote_supported_langs = self._client.get_objects("res.lang")

        return [
            Partner.build_from(
                odoo_client=self._client,
                partner=partner,
                remote_supported_langs=remote_supported_langs,
            )
            for partner in partners
        ]

    def sync_users(self, users):
        remote_users_obj = self._client["res.partner"]
        remote_supported_langs = self._client.get_objects("res.lang")
        for user in users:
            copy_user = user.copy()

            del copy_user["id"]
            # copy_user['login'] = copy_user['email']
            if "language" in copy_user and copy_user["language"]:
                language_iso = copy_user.pop("language")
                for lang in remote_supported_langs:
                    if lang["iso_code"] == language_iso:
                        copy_user["lang"] = lang["code"]
                        break

            if is_empty(copy_user, "type"):
                copy_user["type"] = PartnerAddressType.CONTACT.value

            copy_user["is_company"] = False
            copy_user["active"] = True

            billing_addresses = None
            shipping_addresses = None

            if is_not_empty(copy_user, "billing_addresses"):
                billing_addresses = copy_user.pop("billing_addresses")
            if is_not_empty(copy_user, "shipping_addresses"):
                shipping_addresses = copy_user.pop("shipping_addresses")
            create_remote_user = True
            remote_id = None
            if "_remote_id" in copy_user:
                remote_id = copy_user.pop("_remote_id")
                existing_remote_users = remote_users_obj.search_read(
                    domain=[("active", "in", [True, False]), ("id", "=", remote_id)],
                    fields=["id"],
                )
                if existing_remote_users and len(existing_remote_users) > 0:
                    remote_users_obj.write(remote_id, copy_user)
                    create_remote_user = False
                else:
                    logger.warn(
                        f"User with remote id '{remote_id}' not exists in Odoo, it seems it was deleted there."
                    )
                    logger.info(
                        f"To preserve the integrity of the synchronization, it will be created a new in Odoo."
                    )
                    logger.info(
                        f"Try first to find existing user in Odoo by email '{copy_user['email']}'."
                    )
                    existing_remote_users = remote_users_obj.search_read(
                        domain=[
                            ("active", "in", [True, False]),
                            ("is_company", "=", False),
                            ("email", "=", copy_user["email"]),
                            ("parent_id", "=", False),
                        ],
                        fields=["id"],
                    )  # not required this condition:  copy_user['type'] = self.PartnerAddressType.CONTACT.value, since by email paretn contacts should be unique
                    if existing_remote_users and len(existing_remote_users) > 0:
                        remote_id = existing_remote_users[0]["id"]
                        logger.info(
                            f"Found user with remote id '{remote_id}' and it will be updated."
                        )
                        remote_users_obj.write(remote_id, copy_user)
                        create_remote_user = False
                    else:
                        logger.info(
                            f"No user found in Odoo. Try to create anew in Odoo."
                        )

            if create_remote_user:
                remote_id = remote_users_obj.create(copy_user)
                copy_user["_remote_id"] = remote_id
                user["_remote_id"] = remote_id

            # UserExternal.all_objects.update_or_create(
            #     user_id=user["id"], defaults={"odoo_id": remote_id, "is_removed": False}
            # )
            self._repo.insert(
                key=RedisKeys.USERS,
                entity=OdooUser(
                    odoo_id=remote_id,
                    sync_date=datetime.now(timezone.utc),
                    user=user["id"],
                ),
            )

            if billing_addresses:
                for billing_address in billing_addresses:
                    if remote_id and (
                        is_empty(billing_address, "_remote_id")
                        or is_not_empty(billing_address, "_remote_id")
                        and billing_address["_remote_id"] != remote_id
                    ):
                        billing_address["parent_id"] = remote_id
                    billing_address["type"] = PartnerAddressType.INVOICE.value
                    self.sync_partner(billing_address)
            if shipping_addresses:
                for shipping_address in shipping_addresses:
                    if remote_id and (
                        is_not_empty(shipping_address, "_remote_id")
                        or is_not_empty(shipping_address, "_remote_id")
                        and shipping_address["_remote_id"] != remote_id
                    ):
                        shipping_address["parent_id"] = remote_id
                    shipping_address["type"] = PartnerAddressType.DELIVERY.value
                    self.sync_partner(shipping_address)

        # sync deleted local addresses with remote partners
        logger.info(f"Deleting unused addresses.")
        # external_addresses_for_delete = AddressExternal.all_objects.filter(
        #     address_id__isnull=True, original_address_id__isnull=False
        # )
        external_addresses_for_delete = []
        if external_addresses_for_delete and external_addresses_for_delete.count() > 0:
            delete_remote_ids = [
                o
                for o in external_addresses_for_delete.values_list("odoo_id", flat=True)
            ]
            existing_ids = remote_users_obj.search_read(
                domain=[
                    ("id", "in", delete_remote_ids),
                    ("active", "in", [True, False]),
                ],
                fields=["id"],
            )  # note: always use this 'active' criteria for unlink
            if existing_ids is not None:
                for remote_id in delete_remote_ids:
                    if {"id": remote_id} not in existing_ids:
                        logger.warn(
                            f"The address with remote_id '{remote_id}' not found in Odoo, seems was not synced properly, deleting this external link record locally."
                        )
                if len(existing_ids) > 0:
                    try:
                        remote_users_obj.unlink(ids=[p["id"] for p in existing_ids])
                    except JSONRPCError as exc:
                        logger.error(
                            f"It some addresses with remote ids '{[p['id'] for p in existing_ids]}' can't be deleted in Odoo, cause it might be used. Deleting these external link records locally."
                        )
                        logger.error(f"{str(exc)}")
            external_addresses_for_delete.delete()

    def sync_partner(self, partner):
        client = self._client
        remote_partner_obj = client["res.partner"]
        # if '_remote_id' not in partner:
        #     remote_users = remote_partner_obj.search_read([("email", "=", partner['email'])])
        #     if remote_users:
        #         for remote in remote_users:
        #             partner['_remote_id'] = remote['id']
        #             break
        remote_country_obj = client["res.country"]
        remote_state_obj = client["res.country.state"]
        remote_supported_langs = client["res.lang"].search_read(domain=[])
        send_partner = {
            "name": partner["name"],
            "email": partner["email"],
            "street": partner["address_one"],
            "zip": partner["postal_code"],
            "is_company": False,
            "active": True,
        }
        if "address_two" in partner:
            send_partner["street2"] = partner["address_two"]
        # if 'vat' in partner:  # todo: check format it should as in odoo
        #     send_partner['vat'] = partner['vat']

        if "website" in partner:
            send_partner["website"] = partner["website"]
        if "comment" in partner:
            send_partner["comment"] = partner["comment"]
        if "phone" in partner:
            send_partner["phone"] = partner["phone"]
        if "city" in partner:
            send_partner["city"] = partner["city"]
        if "parent_id" in partner:
            send_partner["parent_id"] = partner["parent_id"]
        if "type" in partner:
            send_partner["type"] = partner["type"]

        if "language" in partner and partner["language"]:
            language_iso = partner["language"]
            for lang in remote_supported_langs:
                if lang["iso_code"] == language_iso or (
                    "_" in lang["iso_code"] and lang["iso_code"][:2] == language_iso
                ):
                    send_partner["lang"] = lang["code"]
                    break
        if "country" in partner and partner["country"]:
            remote_countries = remote_country_obj.search_read(
                [("name", "=", partner["country"])]
            )
            if remote_countries:
                for remote_country in remote_countries:
                    send_partner["country_id"] = remote_country["id"]
                    break
            if "region" in partner and partner["region"]:
                remote_states = remote_state_obj.search_read(
                    [("name", "=", partner["region"])]
                )
                if remote_states:
                    for remote_state in remote_states:
                        send_partner["state_id"] = remote_state["id"]
                        break
        create_remote_partner = True
        remote_id = None
        if "_remote_id" in partner:
            remote_id = partner["_remote_id"]
            existing_remote_partners = remote_partner_obj.search_read(
                domain=[("id", "=", remote_id), ("active", "in", [True, False])],
                fields=["id"],
            )
            if existing_remote_partners and len(existing_remote_partners) > 0:
                if (
                    is_not_empty(send_partner, "parent_id")
                    and remote_id == send_partner["parent_id"]
                ):
                    del send_partner["parent_id"]
                remote_partner_obj.write(remote_id, send_partner)
                create_remote_partner = False
            else:
                logger.warn(
                    f"User with remote id '{remote_id}' not exists in Odoo, it seems it was deleted there. "
                )
                if remote_id:
                    # AddressExternal.all_objects.filter(odoo_id=remote_id).delete()
                    self._repo.remove(key=RedisKeys.ADDRESSES, entity_id=remote_id)

        if create_remote_partner:
            remote_id = remote_partner_obj.create(send_partner)

        partner["_remote_id"] = remote_id
        send_partner["id"] = remote_id
        # AddressExternal.objects.update_or_create(
        #     address_id=partner["id"], odoo_id=remote_id, defaults={"is_removed": False}
        # )
        self._repo.insert(
            key=RedisKeys.ADDRESSES,
            entity=OdooAddress(
                odoo_id=remote_id,
                sync_date=datetime.now(timezone.utc),
                address=partner["id"],
                original_address_id=partner["id"],
            ),
        )
        return send_partner

    def get_products(self, from_date: Optional[datetime] = None) -> dict[str, Any]:
        products = self.get_remote_updated_objects(
            "product.template",
            from_date=from_date,
            i18n_fields=["name"],
            filter_criteria=[("is_published", "=", True), ("list_price", ">", 0.0)],
        )

        product_names = get_entity_name_as_i18n(products)

        result = []

        for product in products:
            group_dto = {
                "id": product["id"],
                "_remote_id": product["id"],
                "names": product_names[product["id"]],
            }
            i18n_fields = get_i18n_field_as_dict(product, "name")
            group_dto.update(i18n_fields)

            for field_name in [
                "display_name",
                "name",
                "barcode",
                "default_code",
                "image_1920",
                "categ_id",
            ]:
                if product[field_name]:
                    group_dto[field_name] = product[field_name]

            result.append(group_dto)

        return {
            "all_ids": self._client.get_all_object_ids(
                "product.template",
                [("is_published", "=", True), ("list_price", ">", 0.0)],
            ),
            "objects": result,
        }

    def get_remote_updated_objects(
        self,
        remote_object_name,
        object_external=None,
        from_date=None,
        sync_from_last_time=False,
        i18n_fields=None,
        filter_criteria=None,
    ):
        api_filter_criteria = []
        if filter_criteria and isinstance(filter_criteria, list):
            api_filter_criteria.extend(filter_criteria)

        if sync_from_last_time and object_external:
            from_date = object_external.objects.order_by("sync_date").last().sync_date

        if from_date:
            last_sync_date_str = from_date.strftime("%Y-%m-%d %H:%M:%S")
            api_filter_criteria.append(("write_date", ">=", last_sync_date_str))

        remote_ids = None
        if object_external:
            remote_ids = [
                external.odoo_id for external in object_external.objects.all()
            ]

        if remote_ids:
            items_limit = 100
            if len(remote_ids) > items_limit:
                objects_parts = []
                for id_range in range(0, len(remote_ids), items_limit):
                    local_api_filter_criteria = [
                        ("id", "in", remote_ids[id_range : id_range + items_limit])
                    ]
                    objects_parts += self._client.get_objects(
                        remote_object_name,
                        api_filter_criteria + local_api_filter_criteria,
                        i18n_fields=i18n_fields,
                    )
                remote_objects = objects_parts
            else:
                api_filter_criteria.append(("id", "in", remote_ids))
                remote_objects = self._client.get_objects(
                    remote_object_name, api_filter_criteria, i18n_fields=i18n_fields
                )
        else:
            remote_objects = self._client.get_objects(
                remote_object_name, api_filter_criteria, i18n_fields=i18n_fields
            )
        return remote_objects

    def get_product_variants(
        self, from_date: Optional[datetime] = None
    ) -> dict[str, Any]:
        product_variants = self.get_remote_updated_objects(
            "product.product",
            from_date=from_date,
            i18n_fields=["display_name"],
            filter_criteria=[("is_published", "=", True), ("list_price", ">", 0.0)],
        )
        product_template_attributes = self.get_remote_updated_objects(
            "product.template.attribute.value", i18n_fields=["name"]
        )
        discounts = self._client.get_discounts()

        def get_attribute(attribute_ids):
            if product_template_attributes and attribute_ids:
                result_ids = []
                for attribute in product_template_attributes:
                    if "id" in attribute and attribute["id"] in attribute_ids:
                        result_ids.extend(
                            self._client.get_object(
                                attribute["product_attribute_value_id"]
                            )
                        )
                return result_ids

        product_variants_names = get_entity_name_as_i18n(
            product_variants, prefix="display_name_"
        )

        result = []
        for product_variant in product_variants:
            product_variant_dto = {
                "id": product_variant["id"],
                "_remote_id": product_variant["id"],
                "name": product_variant["display_name"],
            }
            i18n_fields = get_i18n_field_as_dict(product_variant, "display_name")
            product_variant_dto.update(i18n_fields)

            if discounts:
                product_variant_dto["price_discounts"] = discounts

            if "barcode" in product_variant and product_variant["barcode"]:
                product_variant_dto["barcode"] = product_variant["barcode"]
            if "display_name" in product_variant and product_variant["display_name"]:
                product_variant_dto["display_name"] = product_variant["display_name"]
            if "code" in product_variant and product_variant["code"]:
                product_variant_dto["code"] = product_variant["code"]
            if "partner_ref" in product_variant and product_variant["partner_ref"]:
                product_variant_dto["ref"] = product_variant["partner_ref"]
            if "lst_price" in product_variant and product_variant["lst_price"]:
                product_variant_dto["price"] = product_variant["lst_price"]
            elif "list_price" in product_variant and product_variant["list_price"]:
                logger.warn(
                    f"Product '{product_variant['display_name']}' has no 'lst_price' so setting 'list_price'."
                )
                product_variant_dto["price"] = product_variant["list_price"]
            if "image_1920" in product_variant and product_variant["image_1920"]:
                product_variant_dto["image"] = product_variant["image_1920"]
            if "volume" in product_variant and product_variant["volume"]:
                product_variant_dto["attr_volume"] = product_variant["volume"]
            if (
                "volume_uom_name" in product_variant
                and product_variant["volume_uom_name"]
            ):
                product_variant_dto["attr_volume_name"] = product_variant[
                    "volume_uom_name"
                ]
            if "weight" in product_variant and product_variant["weight"]:
                product_variant_dto["attr_weight"] = product_variant["weight"]
            if (
                "weight_uom_name" in product_variant
                and product_variant["weight_uom_name"]
            ):
                product_variant_dto["attr_weight_name"] = product_variant[
                    "weight_uom_name"
                ]
            if "color" in product_variant and product_variant["color"]:
                product_variant_dto["attr_color"] = product_variant["color"]
            if "uom_name" in product_variant and product_variant["uom_name"]:
                product_variant_dto["attr_unit"] = product_variant["uom_name"]
            if (
                "base_unit_count" in product_variant
                and product_variant["base_unit_count"]
            ):
                product_variant_dto["unit_count"] = product_variant["base_unit_count"]
            if (
                "base_unit_price" in product_variant
                and product_variant["base_unit_price"]
            ):
                product_variant_dto["unit_price"] = product_variant["base_unit_price"]
            if (
                "product_template_attribute_value_ids" in product_variant
                and product_variant["product_template_attribute_value_ids"]
            ):
                product_variant_dto["attribute_values"] = get_attribute(
                    product_variant["product_template_attribute_value_ids"]
                )
            if (
                product_variant["public_categ_ids"]
                and len(product_variant["public_categ_ids"]) > 0
            ):
                product_variant_dto["category"] = self._client.get_object(
                    product_variant["public_categ_ids"]
                )
            if (
                product_variant["product_tmpl_id"]
                and len(product_variant["product_tmpl_id"]) > 0
            ):
                product_variant_dto["group"] = self._client.get_object(
                    product_variant["product_tmpl_id"]
                )
            if (
                product_variant["product_variant_ids"]
                and len(product_variant["product_variant_ids"]) > 0
            ):
                product_variant_dto["product_variant"] = self._client.get_object(
                    product_variant["product_variant_ids"]
                )
            if (
                product_variant["attribute_line_ids"]
                and len(product_variant["attribute_line_ids"]) > 0
            ):
                product_variant_dto["attr_dynamic"] = self._client.get_object(
                    product_variant["attribute_line_ids"]
                )
            product_variant_dto["names"] = product_variants_names[product_variant["id"]]
            result.append(product_variant_dto)
        return {
            "all_ids": self._client.get_all_object_ids(
                "product.product",
                [("is_published", "=", True), ("list_price", ">", 0.0)],
            ),
            "objects": result,
        }

    def get_categories(self, from_date: Optional[datetime] = None) -> dict[str, Any]:
        categories = self.get_remote_updated_objects(
            "product.public.category", from_date=from_date, i18n_fields=["name"]
        )

        parent_codes = {
            parent["id"]: parent["name"]
            for parent in categories
            if not parent["parent_id"]
        }

        category_names = get_entity_name_as_i18n(categories)

        result = [
            {
                "id": category["id"],
                "_remote_id": category["id"],
                "name": category["name"],
                **get_i18n_field_as_dict(category, "name"),
                "parent": self._client.get_object(category["parent_id"])[0]
                if category["parent_id"]
                else None,
                "groups": self._client.get_object(category["product_tmpl_ids"])
                if category["product_tmpl_ids"]
                else None,
                "child": self._client.get_object(category["child_id"])
                if category["child_id"]
                else None,
                "parent_code": parent_codes[category["parent_id"][0]]
                if category["parent_id"]
                else "root",
                "names": category_names[category["id"]],
            }
            for category in categories
        ]

        return {
            "all_ids": self._client.get_all_object_ids("product.public.category"),
            "objects": result,
        }

    def get_product_attributes(
        self, from_date: Optional[datetime] = None, attribute_from_date=None
    ):
        attributes = self.get_remote_updated_objects(
            "product.attribute", from_date=from_date, i18n_fields=["name"]
        )

        attribute_values = self.get_remote_updated_objects(
            "product.attribute.value",
            from_date=attribute_from_date,
            i18n_fields=["name"],
        )

        result = []

        if attributes:
            for attribute in attributes:
                attribute_dto = {"id": attribute["id"], "name": attribute["name"]}
                attribute_dto.update(get_i18n_field_as_dict(attribute, "name"))

                if attribute["product_tmpl_ids"]:
                    attribute_dto["groups"] = self._client.get_object(
                        attribute["product_tmpl_ids"]
                    )

                result.append(attribute_dto)

        if attribute_values:
            for attribute_value in attribute_values:
                attribute_id = attribute_value["attribute_id"]

                if (
                    attribute_id
                    and isinstance(attribute_id, list)
                    and len(attribute_id) > 1
                ):
                    for attribute in result:
                        if "id" in attribute and attribute["id"] == attribute_id[0]:
                            attribute.setdefault("values", [])
                            attribute_value_dto = {
                                "id": attribute_value["id"],
                                "name": attribute_value["name"],
                                "position": attribute_value["sequence"],
                            }
                            attribute_value_dto.update(
                                get_i18n_field_as_dict(attribute_value, "name")
                            )
                            attribute["values"].append(attribute_value_dto)
                else:
                    print(f"There is no attribute for value {attribute_value}")

        return {
            "all_ids": self._client.get_all_object_ids("product.attribute"),
            "objects": result,
            "attribute_values": {
                "all_ids": self._client.get_all_object_ids("product.attribute.value"),
                "objects": None,
            },
        }

    def get_units(self) -> list[dict[str, Any]]:
        logger.info("Receiving units from Odoo")
        units = self.get_remote_updated_objects("uom.uom", i18n_fields=["name"])

        units_names = get_entity_name_as_i18n(units)
        return [
            {
                "name": unit["name"],
                "names": units_names[unit["id"]],
                "code": unit["name"],
            }
            for unit in units
        ]

    def receive_delivery_options(self):
        delivery_options = self._client.get_objects(
            "delivery.carrier", i18n_fields=["name"]
        )
        result = []
        for delivery_option in delivery_options:
            delivery_option_dto = {
                "id": delivery_option["id"],
                "_remote_id": delivery_option["id"],
                "name": delivery_option["name"],
            }
            i18n_fields = get_i18n_field_as_dict(delivery_option, "name")
            delivery_option_dto.update(i18n_fields)
            result.append(delivery_option_dto)
        return {
            "all_ids": self._client.get_all_object_ids(
                "delivery.carrier", [("is_published", "=", True)]
            )(),
            "objects": result,
        }

    def receive_warehouses(self):
        warehouses = self._client.get_objects("stock.warehouse", i18n_fields=["name"])
        result = []
        for warehouse in warehouses:
            warehouse_dto = {
                "id": warehouse["id"],
                "_remote_id": warehouse["id"],
                "name": warehouse["name"],
            }
            result.append(warehouse_dto)
        return {
            "all_ids": self._client.get_all_object_ids("stock.warehouse")(),
            "objects": result,
        }

    def sync_orders(self, orders) -> None:
        if not orders:
            return
        remote_orders_obj = self._client["sale.order"]
        remote_orders_line_obj = self._client["sale.order.line"]
        for order_dto in orders:
            send_order = {
                "order_line": [],
            }

            billing_address_dto = order_dto.get("billing_address")
            shipping_address_dto = order_dto.get("shipping_address")
            delivery_option_dto = order_dto.get("delivery_option")
            warehouse_dto = (
                order_dto["warehouse"]
                if "warehouse" in order_dto and order_dto["warehouse"]
                else None
            )
            basket_dto = order_dto["basket"]

            if is_not_empty(order_dto, "user_remote_id"):
                send_order["partner_id"] = order_dto["user_remote_id"]

            # default type
            if billing_address_dto:
                billing_address_dto["type"] = PartnerAddressType.INVOICE.value
                self.sync_partner(billing_address_dto)
                check_remote_id(billing_address_dto)
                send_order.update(
                    {
                        # "partner_id": billing_address_dto["_remote_id"],
                        "partner_invoice_id": billing_address_dto["_remote_id"],
                    }
                )

            if shipping_address_dto:
                shipping_address_dto["type"] = PartnerAddressType.DELIVERY.value
                self.sync_partner(shipping_address_dto)
                check_remote_id(shipping_address_dto)
                send_order.update(
                    {
                        # "partner_id": shipping_address_dto["_remote_id"],
                        "partner_shipping_id": shipping_address_dto["_remote_id"],
                    }
                )

            if delivery_option_dto:
                if "_remote_id" in delivery_option_dto:
                    send_order["carrier_id"] = delivery_option_dto["_remote_id"]

            send_order.update(
                {
                    "reference": order_dto["name"],
                    "name": order_dto["name"],
                    "amount_tax": basket_dto["total_taxes"],
                    "amount_total": basket_dto["grand_total"],
                    "amount_untaxed": basket_dto["total"],
                }
            )

            if "note" in order_dto:
                send_order["note"] = order_dto["note"]

            if warehouse_dto and "_remote_id" in warehouse_dto:
                send_order["warehouse_id"] = warehouse_dto["_remote_id"]
            else:
                logger.info(
                    f"Sending order id '{order_dto['id']}' has no order warehouse. Please make full sync with Odoo first."
                )
            create_remote_order = True
            remote_order_id = None
            odoo_order = self._repo.get(key=RedisKeys.ORDERS, entity_id=order_dto["id"])
            if "_remote_id" in order_dto:
                remote_order_id = order_dto["_remote_id"]
                existing_remote_orders = remote_orders_obj.read(ids=[remote_order_id])
                if existing_remote_orders and len(existing_remote_orders) > 0:
                    existing_remote_order = existing_remote_orders[0]
                    if (
                        existing_remote_order["state"] != OrderStatus.CANCEL_STATUS
                        and order_dto["status"] == OrderStatus.CANCELLED_BY_ADMIN_STATUS
                    ):
                        send_order["state"] = OrderStatus.CANCEL_STATUS
                    remote_orders_obj.write(remote_order_id, send_order)
                    create_remote_order = False

            if create_remote_order:
                send_order["state"] = OrderStatus.SALE_STATUS
                remote_order_id = remote_orders_obj.create(send_order)
                order_dto["_remote_id"] = remote_order_id
            if remote_order_id:
                existing_remote_orders = remote_orders_obj.read(ids=[remote_order_id])
                defaults = {}
                if existing_remote_orders and len(existing_remote_orders) > 0:
                    existing_remote_order = existing_remote_orders[0]
                    defaults["odoo_order_status"] = existing_remote_order["state"]
                    defaults["odoo_invoice_status"] = existing_remote_order[
                        "invoice_status"
                    ]
                if odoo_order:
                    defaults["order_id"] = order_dto["id"]
                    defaults["odoo_id"] = remote_order_id
                    self._repo.insert(
                        key=RedisKeys.ORDERS,
                        entity=OdooOrder(
                            odoo_id=remote_order_id,
                            order=odoo_order.id,
                            odoo_order_status=defaults["odoo_order_status"],
                            odoo_invoice_status=defaults["odoo_invoice_status"],
                        ),
                    )
                else:
                    self._repo.insert(
                        key=RedisKeys.ORDERS,
                        entity=OdooOrder(
                            odoo_id=remote_order_id,
                            order=order_dto["id"],
                            odoo_order_status=defaults["odoo_order_status"],
                            odoo_invoice_status=defaults["odoo_invoice_status"],
                        ),
                    )
            if "basket_products" in basket_dto:
                for basket_product in basket_dto["basket_products"]:
                    send_order_line = {
                        "order_id": remote_order_id,
                        "price_unit": basket_product["price"],
                        "product_uom_qty": basket_product["quantity"],
                        "price_total": basket_product["total_price"],
                    }

                    if "product" in basket_product:
                        product = basket_product["product"]
                        if "_remote_id" in product:
                            send_order_line["product_id"] = product[
                                "_remote_id"
                            ]  # not id

                        send_order_line["name"] = product["name"]
                    if not create_remote_order and "_remote_id" in basket_product:
                        remote_order_sale_id = basket_product["_remote_id"]
                        remote_orders_line_obj.write(
                            remote_order_sale_id, send_order_line
                        )
                    else:
                        remote_order_sale_id = remote_orders_line_obj.create(
                            send_order_line
                        )
                        basket_product["_remote_id"] = remote_order_sale_id
                    odoo_basket_product = self._repo.get(
                        key=RedisKeys.BASKET_PRODUCT, entity_id=basket_product["id"]
                    )
                    if odoo_basket_product:
                        self._repo.insert(
                            key=RedisKeys.BASKET_PRODUCT,
                            entity=OdooBasketProduct(
                                odoo_id=remote_order_sale_id,
                                basket_product=basket_product["id"],
                            ),
                        )
                    else:
                        self._repo.insert(
                            key=RedisKeys.BASKET_PRODUCT,
                            entity=OdooBasketProduct(
                                odoo_id=remote_order_sale_id,
                                basket_product=basket_product["id"],
                            ),
                        )

    def receive_orders(self, from_date=None):
        if not self._repo.get_len(RedisKeys.ORDERS):
            logger.info(
                "There are no order were send to Odoo, seems no orders created yet.",
                "INFO",
            )
            return None

        orders = self.get_remote_updated_objects("sale.order", OdooOrder, from_date)

        # TODO: Fix
        # orders_invoice_attach_pending = OrderExternal.objects.filter(odoo_order_status__exact=OrderExternal.SALE_STATUS,
        #                                                              odoo_invoice_status__exact=OrderExternal.INV_INVOICED_STATUS).exclude(
        #     order__status__in=[Order.PROCESSED_STATUS, Order.PENDING_PAYMENT_STATUS]).values_list('odoo_id', flat=True)
        orders_invoice_attach_pending = []
        if orders_invoice_attach_pending:
            status_check_orders = self._client.get_objects(
                "sale.order", [("id", "in", [i for i in orders_invoice_attach_pending])]
            )
            if status_check_orders:
                current_order_ids = []
                if orders:
                    current_order_ids = [o["id"] for o in orders]
                for sto in status_check_orders:
                    if sto["id"] not in current_order_ids:
                        orders.append(sto)

        remote_orders_line_obj = self._client["sale.order.line"]

        result = []
        for order in orders:
            order_dto = {
                "id": order["id"],
                "_remote_id": order["id"],
                "name": order["reference"],
                "user_id": self._client.get_object_id(order["partner_id"]),
                "status": order["state"],
                "invoice_status": order["invoice_status"],
                "partner_id": self._client.get_object_id(order["partner_id"]),
                "billing_address": self._client.get_object_id(
                    order["partner_invoice_id"]
                ),
                "shipping_address": self._client.get_object_id(
                    order["partner_shipping_id"]
                ),
                "total_taxes": order["amount_tax"],
                "grand_total": order["amount_total"],
            }

            if "note" in order:
                order_dto["note"] = order["note"]

            order_dto["delivery_date"] = order["commitment_date"]
            order_dto["total"] = order["amount_untaxed"]
            if "invoice_ids" in order and len(order["invoice_ids"]) > 0:
                order_dto["invoice_ids"] = order["invoice_ids"]
                attachment_ids = self._client["account.move"].search_read(
                    [("id", "in", order["invoice_ids"])],
                    fields=["id", "name", "message_main_attachment_id"],
                )
                if attachment_ids and len(attachment_ids) > 0:
                    attachment_id = attachment_ids[0]
                    if (
                        attachment_id
                        and "message_main_attachment_id" in attachment_id
                        and attachment_id["message_main_attachment_id"]
                        and len(attachment_id["message_main_attachment_id"]) > 0
                    ):
                        invoice_file_id = attachment_id["message_main_attachment_id"][0]
                        invoice_file_name = attachment_id["message_main_attachment_id"][
                            1
                        ]
                        attachment = self._client["ir.attachment"].search_read(
                            [("id", "=", invoice_file_id)]
                        )
                        if attachment and len(attachment) > 0:
                            attachment = attachment[0]
                            if (
                                "datas" in attachment
                                and attachment["datas"]
                                and len(attachment["datas"]) > 0
                            ):
                                invoice_file_data = attachment["datas"]
                                order_dto["invoice_file_data"] = invoice_file_data
                                order_dto["invoice_file_name"] = invoice_file_name

            # order_dto["delivery_option"] = order_dto["carrier_id"]
            if "warehouse_id" in order:
                order_dto["warehouse"] = self._client.get_object_id(
                    order["warehouse_id"]
                )
            # order_dto["basket"] = order_dto["amount_untaxed"]

            order_lines = remote_orders_line_obj.search_read(
                [("order_id", "=", order["id"])]
            )
            # default type
            # billing_address_dto['type'] = 'contact'
            # shipping_address_dto['type'] = 'contact'
            order_line_dtos = []
            if order_lines:
                for order_line in order_lines:
                    order_line_dto = {
                        "order_id": self._client.get_object_id(order_line["order_id"]),
                        "price": order_line["price_unit"],
                        "quantity": order_line["product_uom_qty"],
                        "total_price": order_line["price_total"],
                    }
                    if "product_id" in order_line:
                        product_id = self._client.get_object_id(
                            order_line["product_id"]
                        )
                        if product_id:
                            odoo_product = self._repo.get(
                                key=RedisKeys.PRODUCT_VARIANTS, entity_id=product_id
                            )
                            if odoo_product:
                                product = odoo_product.product
                                order_line_dto["product_id"] = product.id
                                order_line_dto["name"] = product.name
                            else:
                                msg = f"Odoo product for remote_id = {product_id} not found. Please sync products first to make this working properly."
                                logger.error(msg)
                                raise OdooSyncException(msg)
                            order_line_dto["_remote_product_id"] = product_id  # not id
                        else:
                            logger.warn(
                                f"Order '{order_dto['name']}' has item '{(order_line['display_type'] + '/' if 'display_type' in order_line else '') + (order_line['name'] if 'name' in order_line else '')}' which is ignored."
                            )
                    order_line_dtos.append(order_line_dto)
                order_dto["order_lines"] = order_line_dtos
            result.append(order_dto)

        return result


# @lru_cache()
def get_odoo_provider(
    odoo_client: Annotated[OdooClient, Depends(get_odoo_client)],
    odoo_repo: Annotated[OdooRepo, Depends(get_odoo_repo)],
) -> OdooManager:
    return OdooManager(odoo_client, odoo_repo)