from typing import Any

import structlog

from .odoo_manager import OdooManager

logger = structlog.getLogger(__name__)


def handle_order_created(odoo_manager: OdooManager, **kwargs: dict[str, Any]) -> None:
    logger.info(f"Syncing Order with Odoo from Ordercast => {kwargs['order']['id']}")
    odoo_manager.sync_orders([kwargs["order"]])


class WebhookHandler:
    HANDLERS = {"order-created": handle_order_created}

    def __init__(self, odoo_manager: OdooManager) -> None:
        self.odoo_manager = odoo_manager

    def handle(self, topic: str, **kwargs: dict[str, Any]) -> None:
        logger.info(f"Received event for topic {topic}")
        self.HANDLERS[topic](odoo_manager=self.odoo_manager, **kwargs)
