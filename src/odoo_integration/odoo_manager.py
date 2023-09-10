from datetime import datetime, timezone
from typing import Annotated, Optional

import structlog
from fastapi import Depends
from odoo_rpc_client.connection.jsonrpc import JSONRPCError

from src.data import OdooUser, OdooAddress
from src.data.enums import PartnerType, PartnerAddressType
from src.infrastructure import OdooClient, get_odoo_client
from .helpers import is_empty, is_not_empty, get_i18n_field_as_dict
from .odoo_repo import OdooRepo, get_odoo_repo, OdooKeys
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

        if users:
            result = []
            addresses = self.receive_partners(
                parent_ids=[u["id"] for u in users], partner_type=PartnerType.ADDRESS
            )
            for user in users:
                # user_dto = {'id': user['id'], 'name': user['name'], 'email': user['email']}

                billing_addresses = []
                shipping_addresses = []
                if addresses:
                    for address in addresses:
                        if address["parent_id"] == user["id"]:
                            if address["type"] == PartnerAddressType.INVOICE.value:
                                billing_addresses.append(address)
                            elif address["type"] == PartnerAddressType.DELIVERY.value:
                                shipping_addresses.append(address)
                user["billing_addresses"] = billing_addresses
                user["shipping_addresses"] = shipping_addresses
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
                key=OdooKeys.USERS,
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
                    self._repo.remove(key=OdooKeys.ADDRESSES, entity_id=remote_id)

        if create_remote_partner:
            remote_id = remote_partner_obj.create(send_partner)

        partner["_remote_id"] = remote_id
        send_partner["id"] = remote_id
        # AddressExternal.objects.update_or_create(
        #     address_id=partner["id"], odoo_id=remote_id, defaults={"is_removed": False}
        # )
        self._repo.insert(
            key=OdooKeys.ADDRESSES,
            entity=OdooAddress(
                odoo_id=remote_id,
                sync_date=datetime.now(timezone.utc),
                address=partner["id"],
                original_address_id=partner["id"],
            ),
        )
        return send_partner

    def get_product_groups(self, from_date: Optional[datetime]):
        product_groups = self.get_remote_updated_objects(
            "product.template",
            from_date=from_date,
            i18n_fields=["name"],
            filter_criteria=[("is_published", "=", True), ("list_price", ">", 0.0)],
        )
        result = list()
        for product_group in product_groups:
            group_dto = {"id": product_group["id"], "_remote_id": product_group["id"]}
            i18n_fields = get_i18n_field_as_dict(product_group, "name")
            group_dto.update(i18n_fields)
            if product_group["display_name"]:
                group_dto["name"] = product_group["display_name"]
            if product_group["name"]:
                group_dto["name"] = product_group["name"]
            if product_group["barcode"]:
                group_dto["barcode"] = product_group["barcode"]
            if product_group["default_code"]:
                group_dto["ref"] = product_group["default_code"]
            if product_group["image_1920"]:
                group_dto["image"] = product_group["image_1920"]

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
        if filter_criteria and type(filter_criteria) == list:
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

    def get_products(self, from_date=Optional[datetime]):
        products = self.get_remote_updated_objects(
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
                result_ids = list()
                for attribute in product_template_attributes:
                    if "id" in attribute and attribute["id"] in attribute_ids:
                        result_ids.extend(
                            self._client.get_object(
                                attribute["product_attribute_value_id"]
                            )
                        )
                return result_ids

        result = (
            []
        )  # todo: check [(p['product_template_attribute_value_ids'],p['attribute_line_ids']) for p  in products if len(p['product_template_attribute_value_ids']) > 0]
        for product in products:
            product_dto = {
                "id": product["id"],
                "_remote_id": product["id"],
                "name": product["display_name"],
            }
            i18n_fields = get_i18n_field_as_dict(product, "display_name")
            product_dto.update(i18n_fields)

            if discounts:
                product_dto["price_discounts"] = discounts

            if "barcode" in product and product["barcode"]:
                product_dto["barcode"] = product["barcode"]
            if "display_name" in product and product["display_name"]:
                product_dto["display_name"] = product["display_name"]
            if "code" in product and product["code"]:
                product_dto["code"] = product["code"]
            if "partner_ref" in product and product["partner_ref"]:
                product_dto["ref"] = product["partner_ref"]
            if "lst_price" in product and product["lst_price"]:
                product_dto["price"] = product["lst_price"]
            elif "list_price" in product and product["list_price"]:
                logger.warn(
                    f"Product '{product['display_name']}' has no 'lst_price' so setting 'list_price'."
                )
                product_dto["price"] = product["list_price"]
            if "image_1920" in product and product["image_1920"]:
                product_dto["image"] = product["image_1920"]
            if "volume" in product and product["volume"]:
                product_dto["attr_volume"] = product["volume"]
            if "volume_uom_name" in product and product["volume_uom_name"]:
                product_dto["attr_volume_name"] = product["volume_uom_name"]
            if "weight" in product and product["weight"]:
                product_dto["attr_weight"] = product["weight"]
            if "weight_uom_name" in product and product["weight_uom_name"]:
                product_dto["attr_weight_name"] = product["weight_uom_name"]
            if "color" in product and product["color"]:
                product_dto["attr_color"] = product["color"]
            if "uom_name" in product and product["uom_name"]:
                product_dto["attr_unit"] = product["uom_name"]
            if "base_unit_count" in product and product["base_unit_count"]:
                product_dto["unit_count"] = product["base_unit_count"]
            if "base_unit_price" in product and product["base_unit_price"]:
                product_dto["unit_price"] = product["base_unit_price"]
            if (
                "product_template_attribute_value_ids" in product
                and product["product_template_attribute_value_ids"]
            ):
                product_dto["attribute_values"] = get_attribute(
                    product["product_template_attribute_value_ids"]
                )
            if product["public_categ_ids"] and len(product["public_categ_ids"]) > 0:
                product_dto["category"] = self._client.get_object(
                    product["public_categ_ids"]
                )
            if product["product_tmpl_id"] and len(product["product_tmpl_id"]) > 0:
                product_dto["group"] = self._client.get_object(
                    product["product_tmpl_id"]
                )
            if (
                product["product_variant_ids"]
                and len(product["product_variant_ids"]) > 0
            ):
                product_dto["product_variant"] = self._client.get_object(
                    product["product_variant_ids"]
                )
            if product["attribute_line_ids"] and len(product["attribute_line_ids"]) > 0:
                product_dto["attr_dynamic"] = self._client.get_object(
                    product["attribute_line_ids"]
                )
            result.append(product_dto)
        return {
            "all_ids": self._client.get_all_object_ids(
                "product.product",
                [("is_published", "=", True), ("list_price", ">", 0.0)],
            ),
            "objects": result,
        }

    def get_categories(self, from_date=Optional[datetime]):
        categories = self.get_remote_updated_objects(
            "product.public.category", from_date=from_date, i18n_fields=["name"]
        )
        result = []
        for category in categories:
            category_dto = {
                "id": category["id"],
                "_remote_id": category["id"],
                "name": category["name"],
            }
            i18n_fields = get_i18n_field_as_dict(category, "name")
            category_dto.update(i18n_fields)
            if category["parent_id"] and len(category["parent_id"]):
                category_dto["parent"] = self._client.get_object(category["parent_id"])
            if category["product_tmpl_ids"] and len(category["product_tmpl_ids"]) > 0:
                category_dto["groups"] = self._client.get_object(
                    category["product_tmpl_ids"]
                )
            if category["child_id"] and len(category["child_id"]) > 0:
                category_dto["child"] = self._client.get_object(category["child_id"])
            result.append(category_dto)
        return {
            "all_ids": self._client.get_all_object_ids("product.public.category")(),
            "objects": result,
        }

    def get_product_attributes(
        self, from_date=Optional[datetime], attribute_from_date=None
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
                i18n_fields = get_i18n_field_as_dict(attribute, "name")
                attribute_dto.update(i18n_fields)
                if (
                    attribute["product_tmpl_ids"]
                    and len(attribute["product_tmpl_ids"]) > 0
                ):
                    attribute_dto["groups"] = self._client.get_object(
                        attribute["product_tmpl_ids"]
                    )
                result.append(attribute_dto)

        if attribute_values:
            for attribute_value in attribute_values:
                attribute_id = attribute_value["attribute_id"]
                if (
                    attribute_id
                    and type(attribute_id) == list
                    and len(attribute_id) > 1
                ):
                    for attribute in result:
                        if "id" in attribute and attribute["id"] == attribute_id[0]:
                            if "values" not in attribute:
                                attribute["values"] = list()
                            attribute_value_dto = {
                                "id": attribute_value["id"],
                                "name": attribute_value["name"],
                                "position": attribute_value["sequence"],
                            }
                            i18n_fields = get_i18n_field_as_dict(
                                attribute_value, "name"
                            )
                            attribute_value_dto.update(i18n_fields)
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


# @lru_cache()
def get_odoo_provider(
    odoo_client: Annotated[OdooClient, Depends(get_odoo_client)],
    odoo_repo: Annotated[OdooRepo, Depends(get_odoo_repo)],
) -> OdooManager:
    return OdooManager(odoo_client, odoo_repo)
