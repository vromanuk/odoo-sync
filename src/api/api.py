from typing import Annotated

import structlog
from fastapi import APIRouter, Depends

from src.infrastructure import RedisClient, get_redis_client
from src.odoo_integration import OdooSyncManager, get_odoo_sync_manager
from .base_response import Response

logger = structlog.getLogger(__name__)
router = APIRouter(
    prefix="",
)


@router.get(
    "/health",
    summary="Basic healthcheck for a server.",
    response_description="Returns 200 if server could accept connections.",
    tags=["health"],
    response_model=Response,
)
async def health(
    redis_client: Annotated[RedisClient, Depends(get_redis_client)]
) -> Response:
    redis_client.ping()
    return Response(message="OK")


@router.get(
    "/sync",
    summary="Start full sync with Odoo",
    response_description="Returns 200 if sync with Odoo started",
    tags=["sync"],
    response_model=Response,
)
async def sync(
    odoo_sync_manager: Annotated[OdooSyncManager, Depends(get_odoo_sync_manager)]
) -> Response:
    odoo_sync_manager.sync()
    return Response(message="Started full sync")


@router.get(
    "/webhooks/order-created",
    summary="Handle `Order Created` event from Ordercast",
    response_description="Returns 200 if event handled correctly",
    tags=["order-created"],
    response_model=Response,
)
async def handle_order_created(
    odoo_sync_manager: Annotated[OdooSyncManager, Depends(get_odoo_sync_manager)]
) -> Response:
    odoo_sync_manager.handle_webhook(topic="order-created")
    return Response(message="OK")
