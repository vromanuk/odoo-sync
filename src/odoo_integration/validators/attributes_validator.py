from src.odoo_integration.exceptions import OdooSyncException
from src.odoo_integration.helpers import (
    is_empty,
    get_field_with_i18n_fields,
    is_unique_by,
    is_length_not_in_range,
)

import structlog

logger = structlog.getLogger(__name__)


def validate_attributes(attributes) -> None:
    has_error = False
    unique_names_dict = {}
    for attribute in attributes:
        if is_empty(attribute, "id"):
            logger.error(
                f"Received attribute with name '{attribute['name']}' has no remote id. Please correct it in Odoo."
            )
            has_error = True
        field_with_i18n = get_field_with_i18n_fields(attribute, "name")
        for field in field_with_i18n:
            unique_names = unique_names_dict.setdefault(field, set())
            if is_empty(attribute, field):
                logger.error(
                    f"Received attribute with remote id '{attribute['id']}' has no '{field}' field. Please correct it in Odoo."
                )
                has_error = True
            if not is_unique_by(unique_names, attribute, field):
                logger.error(
                    f"Received attribute with '{field}' = '{attribute[field]}' should be unique. Please correct it in Odoo."
                )
                has_error = True
            if is_length_not_in_range(attribute[field], 1, 127):
                logger.error(
                    f"Received attribute with '{field}' = '{attribute[field]}' has more than max 127 symbols. Please correct it in Odoo."
                )
                has_error = True

        if "values" in attribute:
            value_unique_names_dict = {}
            for value in attribute["values"]:
                if is_empty(value, "id"):
                    logger.error(
                        f"Received attribute value with name '{value['name']}' has no remote id. Please correct it in Odoo."
                    )
                    has_error = True
                value_field_with_i18n = get_field_with_i18n_fields(value, "name")
                for field in value_field_with_i18n:
                    value_unique_names = value_unique_names_dict.setdefault(
                        field, set()
                    )
                    if is_empty(value, field):
                        logger.error(
                            f"Received attribute value with remote id '{value['id']}' has no '{field}' field. Please correct it in Odoo."
                        )
                        has_error = True
                    if not is_unique_by(value_unique_names, value, field):
                        logger.error(
                            f"Received attribute value with '{field}' = '{value[field]}' should be unique. Please correct it in Odoo."
                        )
                        has_error = True
                    if is_length_not_in_range(value[field], 1, 191):
                        logger.error(
                            f"Received attribute value with '{field}' = '{value[field]}' has more than max 191 symbols. Please correct it in Odoo."
                        )
                        has_error = True

    if has_error:
        raise OdooSyncException(
            "Attributes has errors. Please correct them in Odoo and try to sync again."
        )
