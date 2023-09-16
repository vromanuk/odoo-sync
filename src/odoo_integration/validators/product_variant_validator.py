import re

import structlog

from src.odoo_integration.exceptions import OdooSyncException
from src.odoo_integration.helpers import (
    is_empty,
    is_unique_by,
    is_length_not_in_range,
    get_field_with_i18n_fields,
    is_not_ref,
)

logger = structlog.getLogger(__name__)


def validate_product_variants(product_variants) -> None:
    unique_refs = set()
    has_error = False
    for product in product_variants:
        if is_empty(product, "id"):
            logger.error(
                f"Received product with name '{product['name']}' has no remote id. Please correct it in Odoo."
            )
            has_error = True
        if is_empty(product, "code"):
            logger.error(
                f"Received product with name '{product['name']}' has no reference code. Please correct it in Odoo."
            )
            has_error = True
        if not is_unique_by(unique_refs, product, "code"):
            logger.error(
                f"Received product with reference code '{product['code']}' should be unique. Please correct it in Odoo."
            )
            has_error = True
        if "code" in product and is_length_not_in_range(product["code"], 1, 191):
            logger.error(
                f"Received product with reference code '{product['code']}' has more than max 191 symbols. Please correct it in Odoo."
            )
            has_error = True
        if "code" in product and is_not_ref(product["code"]):
            logger.error(
                f"Received product with reference code '{product['code']}' should contain only alpha, numbers, hyphen and dot. Please correct it in Odoo."
            )
            has_error = True

        field_with_i18n = get_field_with_i18n_fields(product, "display_name")
        for field in field_with_i18n:
            if is_empty(product, field):
                logger.error(
                    f"Received product with id '{product['id']}' has no '{field}' field. Please correct it in Odoo."
                )
                has_error = True
            else:
                display_name = product[field]
                display_name = re.sub(r"^\[.*] ?", "", display_name)
                if is_length_not_in_range(display_name, 1, 191):
                    logger.error(
                        f"Received product display name '{display_name}' has more than max 191 symbols. Please correct it in Odoo."
                    )
                    has_error = True

    if has_error:
        raise OdooSyncException(
            "Products has errors. Please correct them in Odoo and try to sync again."
        )
