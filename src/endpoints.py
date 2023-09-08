from fastapi import APIRouter

from src.healthcheck import healthcheck_router
from src.odoo_integration import sync_router

api_router = APIRouter()

api_router.include_router(healthcheck_router)
api_router.include_router(sync_router)
