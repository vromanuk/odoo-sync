from fastapi import APIRouter

router = APIRouter(
    prefix="/health",
)


@router.get(
    "/",
    summary="Basic healthcheck for a server.",
    response_description="Returns 200 if server could accept connections.",
    tags=["health"],
)
async def health() -> dict[str, str]:
    return {"msg": "OK"}
