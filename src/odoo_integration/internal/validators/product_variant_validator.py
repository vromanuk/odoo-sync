import re
from typing import Any

import structlog

from ..exceptions import OdooSyncException
from ..utils import (
    is_empty,
    is_unique_by,
    is_length_not_in_range,
    get_field_with_i18n_fields,
    is_not_ref,
)

logger = structlog.getLogger(__name__)


def validate_product_variants(product_variants: list[dict[str, Any]]) -> None:
    product_variants = sorted(product_variants, key=lambda d: d["display_name"])

    if not product_variants:
        return

    unique_refs = set()
    has_error = False
    for product in product_variants:
        if is_empty(product, "id"):
            logger.error(
                f"Received product with name '{product['name']}'"
                f"has no remote id. Please correct it in Odoo."
            )
            has_error = True
        if is_empty(product, "code"):
            logger.error(
                f"Received product with name '{product['name']}'"
                f"has no reference code. Please correct it in Odoo."
            )
            has_error = True
        if not is_unique_by(unique_refs, product, "code"):
            logger.error(
                f"Received product with reference code '{product['code']}'"
                f"should be unique. Please correct it in Odoo."
            )
            has_error = True
        if "code" in product and is_length_not_in_range(product["code"], 1, 191):
            logger.error(
                f"Received product with reference code '{product['code']}'"
                f"has more than max 191 symbols. Please correct it in Odoo."
            )
            has_error = True
        if "code" in product and is_not_ref(product["code"]):
            logger.error(
                f"Received product with reference code {product['code']}"
                f"should contain only alpha, numbers, hyphen and dot. "
                f"Please correct it in Odoo."
            )
            has_error = True

        field_with_i18n = get_field_with_i18n_fields(product, "display_name")
        for field in field_with_i18n:
            if is_empty(product, field):
                logger.error(
                    f"Received product with id '{product['id']}'"
                    f"has no '{field}' field. Please correct it in Odoo."
                )
                has_error = True
            else:
                display_name = product[field]
                display_name = re.sub(r"^\[.*] ?", "", display_name)
                if is_length_not_in_range(display_name, 1, 191):
                    logger.error(
                        f"Received product display name '{display_name}'"
                        f"has more than max 191 symbols. Please correct it in Odoo."
                    )
                    has_error = True

    if has_error:
        raise OdooSyncException(
            "Products has errors. Please correct them in Odoo and try to sync again."
        )
