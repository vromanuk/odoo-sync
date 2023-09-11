import structlog

from src.odoo_integration.exceptions import OdooSyncException
from src.odoo_integration.helpers import (
    is_empty,
    get_field_with_i18n_fields,
    is_unique_by,
    is_length_not_in_range,
)

logger = structlog.getLogger(__name__)


def validate_delivery_options(delivery_options) -> None:
    unique_names_dict = {}
    has_error = False
    for delivery_option in delivery_options:
        if is_empty(delivery_option, "id"):
            logger.error(
                f"Received delivery option with name '{delivery_option['name']}' has no remote id. Please correct it in Odoo."
            )
            has_error = True
        field_with_i18n = get_field_with_i18n_fields(delivery_option, "name")
        for field in field_with_i18n:
            unique_names = unique_names_dict.setdefault(field, set())
            if is_empty(delivery_option, field):
                logger.error(
                    f"Received delivery option with remote id '{delivery_option['id']}' has no '{field}' field. Please correct it in Odoo."
                )
                has_error = True
            if not is_unique_by(unique_names, delivery_option, field):
                logger.error(
                    f"Received delivery option with '{field}' = '{delivery_option[field]}' should be unique. Please correct it in Odoo."
                )
                has_error = True
            if is_length_not_in_range(delivery_option[field], 1, 64):
                logger.error(
                    f"Received delivery option with '{field}' = '{delivery_option[field]}' has more than max 64 symbols. Please correct it in Odoo."
                )
                has_error = True

    if has_error:
        OdooSyncException(
            "Delivery option has errors. Please correct them in Odoo and try to sync again."
        )
