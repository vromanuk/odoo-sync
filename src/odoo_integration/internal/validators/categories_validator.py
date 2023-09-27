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


def validate_categories(categories: dict[str, Any]) -> None:
    categories = categories["objects"]

    if not categories:
        return

    categories = sorted(categories, key=lambda d: d["name"])
    has_error = False
    unique_names_dict = {}

    for category in categories:
        if is_empty(category, "id"):
            logger.error(
                f"Received category with name '{category['name']}'"
                f"has no remote id. Please correct it in Odoo."
            )
            has_error = True

        field_with_i18n = get_field_with_i18n_fields(category, "name")
        for field in field_with_i18n:
            unique_names = unique_names_dict.setdefault(field, set())
            if is_empty(category, field):
                logger.error(
                    f"Received category with remote id '{category['id']}'"
                    f"has no '{field}' field. Please correct it in Odoo."
                )
                has_error = True
            if not is_unique_by(unique_names, category, field):
                logger.error(
                    f"Received category with '{field}' = '{category[field]}'"
                    f"should be unique. Please correct it in Odoo."
                )
                has_error = True
            if is_length_not_in_range(category[field], 1, 127):
                logger.error(
                    f"Received category with '{field}' = '{category[field]}'"
                    f"has more than max 127 symbols. Please correct it in Odoo."
                )
                has_error = True

    if has_error:
        raise OdooSyncException(
            "Categories has errors. Please correct them in Odoo and try to sync again."
        )
