from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import Depends
from odoo_rpc_client.connection.jsonrpc import JSONRPCError

from src.data import OdooUser, OdooAddress
from src.data.enums import PartnerType, PartnerAddressType
from src.infrastructure import OdooClient, get_odoo_client
from .helpers import is_empty, is_not_empty
from .odoo_repo import OdooRepo, get_odoo_repo
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
            self._repo.save_user(
                OdooUser(
                    odoo_id=remote_id,
                    sync_date=datetime.now(timezone.utc),
                    user=user["id"],
                )
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
                    self._repo.remove_address(remote_id)

        if create_remote_partner:
            remote_id = remote_partner_obj.create(send_partner)

        partner["_remote_id"] = remote_id
        send_partner["id"] = remote_id
        # AddressExternal.objects.update_or_create(
        #     address_id=partner["id"], odoo_id=remote_id, defaults={"is_removed": False}
        # )
        self._repo.save_address(
            OdooAddress(
                odoo_id=remote_id,
                sync_date=datetime.now(timezone.utc),
                address=partner["id"],
                original_address_id=partner["id"],
            )
        )
        return send_partner


# @lru_cache()
def get_odoo_provider(
        odoo_client: Annotated[OdooClient, Depends(get_odoo_client)],
        odoo_repo: Annotated[OdooRepo, Depends(get_odoo_repo)],
) -> OdooManager:
    return OdooManager(odoo_client, odoo_repo)
