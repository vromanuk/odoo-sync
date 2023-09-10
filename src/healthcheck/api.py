from typing import Annotated

from fastapi import APIRouter, Depends

from src.infrastructure import RedisClient, get_redis_client

router = APIRouter(
    prefix="/health",
)


@router.get(
    "/",
    summary="Basic healthcheck for a server.",
    response_description="Returns 200 if server could accept connections.",
    tags=["health"],
)
async def health(
    redis_client: Annotated[RedisClient, Depends(get_redis_client)]
) -> dict[str, str]:
    redis_client.ping()
    return {"msg": "OK"}
