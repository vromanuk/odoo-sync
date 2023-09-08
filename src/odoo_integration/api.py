from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends

from src.api import Response
from .odoo_sync_manager import get_odoo_sync_manager, OdooSyncManager

router = APIRouter(
    prefix="/sync",
)

logger = getLogger(__name__)


@router.get(
    "/",
    summary="Start full sync with Odoo",
    response_description="Returns 200 if sync with Odoo started",
    tags=["sync"],
    response_model=Response,
)
async def sync(
    odoo_sync_manager: Annotated[OdooSyncManager, Depends(get_odoo_sync_manager)],
    background_tasks: BackgroundTasks,
) -> Response:
    background_tasks.add_task(odoo_sync_manager.sync)
    # odoo_sync_manager.repo.save_user(
    #     OdooUser(
    #         odoo_id=1,
    #         created_at=datetime.now(timezone.utc),
    #         updated_at=datetime.now(timezone.utc),
    #         sync_date=None,
    #         user=1,
    #     )
    # )
    # odoo_sync_manager.repo.save_users(
    #     [
    #         OdooUser(
    #             odoo_id=2,
    #             created_at=datetime.now(timezone.utc),
    #             updated_at=datetime.now(timezone.utc),
    #             sync_date=None,
    #             user=2,
    #         ),
    #         OdooUser(
    #             odoo_id=3,
    #             created_at=datetime.now(timezone.utc),
    #             updated_at=datetime.now(timezone.utc),
    #             sync_date=None,
    #             user=3,
    #         ),
    #     ]
    # )
    # logger.info(f"{odoo_sync_manager.repo.get_user(1)}, got user")
    #
    # logger.info(f"{odoo_sync_manager.repo.get_users()}, got users")

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
