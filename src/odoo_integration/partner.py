import secrets
from typing import Any

import structlog

from src.data import UserStatus, OrdercastMerchant
from src.infrastructure import OdooClient
from .exceptions import OdooSyncException
from .helpers import is_not_empty, is_empty, is_unique_by, is_length_not_in_range

logger = structlog.getLogger(__name__)


class Partner:
    @classmethod
    def build_from(cls, odoo_client: OdooClient, partner, remote_supported_langs=None):
        partner_dto = {"id": partner["id"], "_remote_id": partner["id"]}
        if is_not_empty(partner, "street"):
            partner_dto["address_one"] = partner["street"]
        if is_not_empty(partner, "zip"):
            partner_dto["postal_code"] = partner["zip"]
        if is_not_empty(partner, "street2"):
            partner_dto["address_two"] = partner["street2"]
        if is_not_empty(partner, "name"):
            partner_dto["name"] = partner["name"]
        if is_not_empty(partner, "email"):
            partner_dto["email"] = partner["email"]
        if is_not_empty(partner, "website"):
            partner_dto["website"] = partner["website"]
        if is_not_empty(partner, "comment"):
            partner_dto["comment"] = partner["comment"]
        if is_not_empty(partner, "phone"):
            partner_dto["phone"] = partner["phone"]
        if is_not_empty(partner, "city"):
            partner_dto["city"] = partner["city"]
        if is_not_empty(partner, "lang") and remote_supported_langs:
            language_iso = partner["lang"]
            for lang in remote_supported_langs:
                if lang["code"] == language_iso:
                    partner_dto["language"] = lang["iso_code"]
                    break
        if is_not_empty(partner, "type"):
            partner_dto["type"] = partner["type"]
        if is_not_empty(partner, "parent_id"):
            partner_dto["parent_id"] = odoo_client.get_object_id(partner["parent_id"])
        # if partner['country_id']:
        #     remote_country = remote_country_obj.search_read([('id', '=', partner['country_id'])])
        #     if remote_country:
        #         partner_dto["country_name"] = remote_country['name']
        if is_not_empty(partner, "country_code"):
            partner_dto["country_code"] = partner["country_code"]
        if is_not_empty(partner, "state_id"):
            if type(partner["state_id"]) == list and len(partner["state_id"]) == 2:
                partner_dto["state_name"] = partner["state_id"][1]
        if is_not_empty(partner, "vat"):
            partner_dto["vat"] = partner["vat"]
        if is_not_empty(partner, "commercial_company_name"):
            partner_dto["company_name"] = partner["commercial_company_name"]
        return partner_dto


def validate_partners(
    partners: list[dict[str, Any]], ordercast_users: list[OrdercastMerchant]
) -> None:
    if not partners:
        return

    existing_ordercast_users = {
        user.erp_id: {"name": user.name, "id": user.id} for user in ordercast_users
    }
    unique_names = set()
    has_error = False

    for user in partners:
        if is_empty(user, "id"):
            logger.error(
                f"Received user with name '{user['name']}' has no remote id. Please correct it in Odoo."
            )
            has_error = True
        if is_empty(user, "name"):
            logger.error(
                f"Received user with id '{user['id']}' has no name. Please correct it in Odoo."
            )
            has_error = True
        if is_empty(user, "email"):
            logger.error(
                f"Received user with id '{user['id']}' has no email. Please correct it in Odoo."
            )
            has_error = True
        if not is_unique_by(unique_names, user, "email"):
            logger.error(
                f"Received user with email '{user['email']}' should be unique. Please correct it in Odoo (check partners which has no children or archived)."
            )
            has_error = True
        if "name" in user and is_length_not_in_range(user["name"], 1, 150):
            logger.error(
                f"Received user with name '{user['name']}' has more than max 150 symbols. Please correct it in Odoo."
            )
            has_error = True

        if user["id"] in existing_ordercast_users:
            ordercast_user = existing_ordercast_users[user["id"]]
            logger.error(
                f"Received user with name `{user['name']}` already exists in Ordercast, id => `{ordercast_user['id']}` and name => `{ordercast_user['name']}`. Please give the another email to this '{user['name']}' partner in Odoo (check partners which has no children or archived)."
            )
            has_error = True

    if has_error:
        raise OdooSyncException(
            "User has errors. Please correct them in Odoo and try to sync again."
        )


def create_partner_data(partner: dict[str, Any]) -> dict[str, Any]:
    language = (
        partner.get("language", "fr")
        if partner.get("language") and len(partner.get("language")) == 2
        else "fr"
    )
    website = (
        partner["website"]
        if not is_empty(partner, "website")
        else "https://shop.company.domain"
    )
    info = partner["comment"] if not is_empty(partner, "comment") else ""

    user_data = {
        "name": partner["name"],
        "erp_id": partner["id"],
        "is_approved": False,
        "is_active": True,
        "is_removed": False,
        "password": secrets.token_urlsafe(nbytes=64),
        "status": UserStatus.NEW,
        "language": language,
        "website": website,
        "info": info,
        "phone": partner.get("phone", "+3281000000"),
        "city": partner.get("city", "Southampton"),
        "postcode": partner.get("postcode", "21701"),
        "street": partner.get("street", "81 Bedford Pl"),
        "vat": partner.get("vat", "BE09999999XX"),
        "email": partner["email"],
        "odoo_data": partner,
    }

    return user_data
