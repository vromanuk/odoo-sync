import secrets
from typing import Any

from src.data import UserStatus
from .helpers import is_empty, get_i18n_field_as_dict, get_entity_name_as_i18n
from .odoo_repo import OdooRepo, RedisKeys


def get_partner_data(partner: dict[str, Any]) -> dict[str, Any]:
    language = (
        partner.get("language", "fr")
        if partner.get("language") and len(partner.get("language", [])) == 2
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


def get_attribute_data(attribute: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": attribute["id"],
        "name": attribute["name"],
        **({"position": attribute["position"]} if "position" in attribute else {}),
        **get_i18n_field_as_dict(attribute, "name"),
        "names": get_entity_name_as_i18n([attribute])[attribute["id"]],
    }


def get_product_data(product: dict[str, Any], odoo_repo: OdooRepo) -> dict[str, Any]:
    return {
        "name": product["name"],
        "is_removed": False,
        "i18n_fields": get_i18n_field_as_dict(product, "name"),
        "names": product["names"],
        "category": odoo_repo.get(RedisKeys.CATEGORIES, product["categ_id"][0]),
        "id": product["id"],
    }


def get_product_variant_data(
    product_variant: dict[str, Any], odoo_repo: OdooRepo
) -> dict[str, Any]:
    remote_id = product_variant["id"]

    i18n_fields = get_i18n_field_as_dict(
        product_variant, "display_name", "name", r"^\[.*] ?"
    )

    defaults = {
        "id": remote_id,
        "name": product_variant["display_name"],
        "pack": product_variant.get("unit_count", 1),
        "product": odoo_repo.get(RedisKeys.PRODUCTS, product_variant["group"][0]),
        "unit": product_variant.get("attr_unit"),
        "barcode": product_variant.get("barcode", ""),
        "ref": product_variant["code"],
        "price": product_variant.get("price"),
        "is_removed": False,
        "names": product_variant["names"],
        "sku": product_variant["code"],
        "attribute_values": [
            odoo_repo.get(RedisKeys.ATTRIBUTES, a["id"])
            for a in product_variant.get("attribute_values", [])
        ],
    }
    defaults.update(i18n_fields)

    return defaults


def get_delivery_option_data(delivery_option: dict[str, Any]) -> dict[str, Any]:
    names = delivery_option.get("names", {})
    return {
        "names": names,
        "name": delivery_option.get("name"),
        "id": delivery_option["id"],
    }


def get_pickup_location_data(pickup_location: dict[str, Any]) -> dict[str, Any]:
    defaults_data = {}

    if "name" in pickup_location and pickup_location["name"]:
        defaults_data = {
            "id": pickup_location["id"],
            "name": pickup_location["name"],
            "names": pickup_location.get("names", {}),
        }
        defaults_data.update(get_i18n_field_as_dict(pickup_location, "name"))

    return defaults_data
