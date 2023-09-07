from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends

from src.api import Response
from .odoo_sync_manager import get_odoo_sync_manager, OdooSyncManager

router = APIRouter(
    prefix="/sync",
)


@router.get(
    "/",
    summary="Start full sync with Odoo",
    response_description="Returns 200 if sync with Odoo started",
    tags=["health"],
    response_model=Response,
)
async def sync(
    odoo_sync_manager: Annotated[OdooSyncManager, Depends(get_odoo_sync_manager)],
    background_tasks: BackgroundTasks,
) -> Response:
    background_tasks.add_task(odoo_sync_manager.sync)
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
