import secrets
from typing import Any

from src.data import UserStatus
from .helpers import is_empty, get_i18n_field_as_dict


def get_partner_data(partner: dict[str, Any]) -> dict[str, Any]:
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


def get_attribute_data(attribute: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": attribute["id"],
        "name": attribute["name"],
        **({"position": attribute["position"]} if "position" in attribute else {}),
        **get_i18n_field_as_dict(attribute, "name"),
    }


def get_product_data(product: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": product["name"],
        "is_removed": False,
        "i18n_fields": get_i18n_field_as_dict(product, "name"),
        "names": product["names"],
        "category": product["categ_id"][0],
        "id": product["id"],
    }


def get_product_variant_data(product_variant: dict[str, Any]) -> dict[str, Any]:
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
        "id": remote_id,
        "name": name,
        "pack": pack,
        "group": group,
        "unit": unit_name,
        "barcode": barcode,
        "ref": ref,
        "price": price,
    }
    defaults.update(i18n_fields)
    defaults["is_removed"] = False

    return defaults
