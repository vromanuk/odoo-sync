import contextvars
from typing import Any

ctx = contextvars.ContextVar("commons")  # type: ignore


def get_ctx() -> Any:
    return ctx.get()


def set_context_value(value: Any) -> None:
    ctx.set(value)
