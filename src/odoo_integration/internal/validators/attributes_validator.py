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


def validate_attributes(attributes: dict[str, Any]) -> None:
    attributes = attributes["objects"]

    if not attributes:
        return

    has_error = False
    unique_names_dict = {}  # type: ignore
    for attribute in attributes:
        if is_empty(attribute, "id"):  # type: ignore
            logger.error(
                f"Received attribute with name '{attribute['name']}' "  # type: ignore
                f"has no remote id. Please correct it in Odoo."
            )
            has_error = True
        field_with_i18n = get_field_with_i18n_fields(attribute, "name")  # type: ignore
        for field in field_with_i18n:
            unique_names = unique_names_dict.setdefault(field, set())
            if is_empty(attribute, field):  # type: ignore
                logger.error(
                    f"Received attribute with remote id '{attribute['id']}' "  # type: ignore  # noqa
                    f"has no '{field}' field. Please correct it in Odoo."
                )
                has_error = True
            if not is_unique_by(unique_names, attribute, field):  # type: ignore
                logger.error(
                    f"Received attribute with '{field}' = '{attribute[field]}' "
                    f"should be unique. Please correct it in Odoo."
                )
                has_error = True
            if is_length_not_in_range(attribute[field], 1, 127):
                logger.error(
                    f"Received attribute with '{field}' = '{attribute[field]}' "
                    f"has more than max 127 symbols. Please correct it in Odoo."
                )
                has_error = True

        if "values" in attribute:
            value_unique_names_dict = {}  # type: ignore
            for value in attribute["values"]:  # type: ignore
                if is_empty(value, "id"):  # type: ignore
                    logger.error(
                        f"Received attribute value with name '{value['name']}'"  # type: ignore # noqa
                        f"has no remote id. Please correct it in Odoo."
                    )
                    has_error = True
                value_field_with_i18n = get_field_with_i18n_fields(value, "name")  # type: ignore # noqa
                for field in value_field_with_i18n:
                    value_unique_names = value_unique_names_dict.setdefault(
                        field, set()
                    )
                    if is_empty(value, field):  # type: ignore
                        logger.error(
                            f"Received attribute value with remote id '{value['id']}'"  # type: ignore # noqa
                            f"has no '{field}' field. Please correct it in Odoo."
                        )
                        has_error = True
                    if not is_unique_by(value_unique_names, value, field):  # type: ignore # noqa
                        logger.error(
                            f"Received attribute value with {field} = {value[field]}"
                            f"should be unique. Please correct it in Odoo."
                        )
                        has_error = True
                    if is_length_not_in_range(value[field], 1, 191):
                        logger.error(
                            f"Received attribute value with {field} = {value[field]}"
                            f"has more than max 191 symbols. Please correct it in Odoo."
                        )
                        has_error = True

    if has_error:
        raise OdooSyncException(
            "Attributes has errors. Please correct them in Odoo and try to sync again."
        )
