from typing import Any

import structlog

from ..exceptions import OdooSyncException
from ..utils import (
    is_empty,
    is_unique_by,
    is_length_not_in_range,
)

logger = structlog.getLogger(__name__)


def validate_pickup_locations(pickup_locations: dict[str, Any]) -> None:
    pickup_locations = pickup_locations["objects"]

    if not pickup_locations:
        return

    unique_names = set()
    has_error = False
    for warehouse in pickup_locations:
        if is_empty(warehouse, "id"):
            logger.error(
                f"Received warehouse with name '{warehouse['name']}'"
                f"has no remote id. Please correct it in Odoo."
            )
            has_error = True
        if is_empty(warehouse, "name"):
            logger.error(
                f"Received warehouse with id '{warehouse['id']}'"
                f"has no name. Please correct it in Odoo."
            )
            has_error = True
        if not is_unique_by(unique_names, warehouse, "name"):
            logger.error(
                f"Received warehouse with name '{warehouse['name']}'"
                f"should be unique. Please correct it in Odoo."
            )
            has_error = True
        if "name" in warehouse and is_length_not_in_range(warehouse["name"], 1, 64):
            logger.error(
                f"Received warehouse with name '{warehouse['name']}'"
                f"has more than max 64 symbols. Please correct it in Odoo."
            )
            has_error = True
    if has_error:
        OdooSyncException(
            "Warehouses has errors. Please correct them in Odoo and try to sync again."
        )
