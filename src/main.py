import logging

import structlog
import uvicorn
from fastapi import FastAPI

from src.commons import set_context_value
from src.config import get_settings
from src.endpoints import api_router

settings = get_settings()
app = FastAPI(title="Odoo Sync", openapi_url="/v1/openapi.json")
app.include_router(api_router, prefix=settings.APP.API_PREFIX)


def configure_logging() -> None:
    env = settings.APP.ENV
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if env == "dev":
        structlog.configure(
            processors=shared_processors + [structlog.dev.ConsoleRenderer()],
            wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=False,
        )
    else:
        structlog.configure(
            processors=shared_processors
            + [
                structlog.processors.dict_tracebacks,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=False,
        )


@app.on_event("startup")
async def startup() -> None:
    set_context_value({})
    configure_logging()


if __name__ == "__main__":
    uvicorn.run("main:app", port=5000, log_level="info")
