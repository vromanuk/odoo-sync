from typing import Annotated

import structlog
from fastapi import APIRouter, Depends

from src.infrastructure import RedisClient, get_redis_client
from src.odoo_integration import SyncManager, get_odoo_sync_manager
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
    odoo_sync_manager: Annotated[SyncManager, Depends(get_odoo_sync_manager)]
) -> Response:
    odoo_sync_manager.sync()
    return Response(message="Started full sync")


# @router.get(
#     "/orders",
#     summary="Start syncing with Odoo, orders only.",
#     response_description="Returns 200 if sync with Odoo started",
#     tags=["health"],
# )
# async def orders_sync(syncer: Depends(get_odoo_sync_manager), background_tasks: BackgroundTasks) -> dict[str, str]:
#     background_tasks.add_task(syncer.sync_orders)
#     return {"msg": "Order sync started"}