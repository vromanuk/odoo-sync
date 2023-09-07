from logging.config import dictConfig

import uvicorn
from fastapi import FastAPI

from src.config import get_settings
from src.endpoints import api_router
from src.infrastructure import OdooClient
from src.log_config import LOGGING

app = FastAPI(title="Odoo Sync", openapi_url="/v1/openapi.json")


@app.on_event("startup")
async def startup():
    settings = get_settings()
    dictConfig(LOGGING)
    app.include_router(api_router, prefix=settings.APP.API_PREFIX)

    odoo_client = OdooClient(settings.ODOO)


if __name__ == "__main__":
    uvicorn.run("main:app", port=5000, log_level="info")
