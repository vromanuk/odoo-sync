import secrets
from typing import Any

from src.data import UserStatus, OrdercastProduct, OrdercastAttribute, OrdercastCategory
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


def get_product_data(
    product: dict[str, Any],
    odoo_categories: list[dict[str, Any]],
    ordercast_categories: list[OrdercastCategory],
) -> dict[str, Any]:
    ordercast_category_mapper = {c.code: c.id for c in ordercast_categories}
    category_mapper = {
        c["id"]: ordercast_category_mapper[c["name"]]
        for c in odoo_categories
        if c["name"] in ordercast_categories
    }

    return {
        "name": product["name"],
        "is_removed": False,
        "i18n_fields": get_i18n_field_as_dict(product, "name"),
        "names": product["names"],
        "category": category_mapper.get(product["categ_id"][0], product["categ_id"][0]),
        "id": product["id"],
    }


def get_product_variant_data(
    product_variant: dict[str, Any],
    odoo_products: list[dict[str, Any]],
    ordercast_products: list[OrdercastProduct],
    odoo_attributes: list[dict, str, Any],
    ordercast_attributes: list[OrdercastAttribute],
) -> dict[str, Any]:
    ordercast_product_mapper = {p.sku: p.id for p in ordercast_products}
    product_mapper = {
        p["id"]: ordercast_product_mapper[p["name"]]
        for p in odoo_products
        if p["name"] in ordercast_product_mapper
    }
    ordercast_attribute_mapper = {a.name: a.id for a in ordercast_attributes}
    attribute_mapper = {
        a["id"]: ordercast_attribute_mapper[a["name"]]
        for a in odoo_attributes
        if a["name"] in ordercast_attribute_mapper
    }

    remote_id = product_variant["id"]

    i18n_fields = get_i18n_field_as_dict(
        product_variant, "display_name", "name", r"^\[.*] ?"
    )

    defaults = {
        "id": remote_id,
        "name": product_variant["display_name"],
        "pack": product_variant.get("unit_count", 1),
        "product_id": product_mapper.get(
            product_variant["group"][0], product_variant["group"][0]
        ),
        "unit": product_variant.get("attr_unit"),
        "barcode": product_variant.get("barcode", ""),
        "ref": product_variant["code"],
        "price": product_variant.get("price"),
        "is_removed": False,
        "names": product_variant["names"],
        "sku": product_variant["code"],
        "attribute_values": [
            attribute_mapper.get(a) for a in product_variant.get("attribute_values", [])
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
