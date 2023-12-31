from typing import Any

import structlog

from ..exceptions import OdooSyncException
from ..utils import (
    is_empty,
    get_field_with_i18n_fields,
    is_unique_by,
    is_length_not_in_range,
)

logger = structlog.getLogger(__name__)


def validate_products(products: dict[str, Any]) -> None:
    products = products["objects"]
    if not products:
        return

    unique_names_dict = {}  # type: ignore
    has_error = False
    for product in products:
        if is_empty(product, "id"):  # type: ignore
            logger.error(
                f"Received group with name '{product['name']}'"  # type: ignore
                f"has no remote id. Please correct it in Odoo."
            )
            has_error = True
        field_with_i18n = get_field_with_i18n_fields(product, "name")  # type: ignore
        for field in field_with_i18n:
            unique_names = unique_names_dict.setdefault(field, set())
            if is_empty(product, field):  # type: ignore
                logger.error(
                    f"Received group with remote id '{product['id']}'"  # type: ignore
                    f"has no '{field}' field. Please correct it in Odoo."
                )
                has_error = True
            if not is_unique_by(unique_names, product, field):  # type: ignore
                logger.error(
                    f"Received group with '{field}' = '{product[field]}'"
                    f"should be unique. Please correct it in Odoo."
                )
                has_error = True
            if is_length_not_in_range(product[field], 1, 191):
                logger.error(
                    f"Received group with '{field}' = '{product[field]}'"
                    f"has more than max 191 symbols. Please correct it in Odoo."
                )
                has_error = True

    if has_error:
        raise OdooSyncException(
            "Groups has errors. Please correct them in Odoo and try to sync again."
        )
