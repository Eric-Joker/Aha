
from typing import overload

from core.config import cfg
from core.identity import aha_id2user
from core.dispatcher import current_event


# region is_super
@overload
async def is_super(platform: str, user_id: str, /) -> bool: ...


@overload
async def is_super(user_id: int, /) -> bool:
    """
    Args:
        user_id (int): Aha ID.
    """


@overload
async def is_super() -> bool:
    """自动从上下文事件获取用户"""


async def is_super(arg1=None, arg2=None, /):
    if arg2:
        return any(arg2 == obj.user_id for obj in cfg.super if arg1 == obj.platform)
    if arg1:
        return any(u.user_id == obj.user_id for obj in cfg.super for u in await aha_id2user(arg1) if u.platform == obj.platform)
    event = current_event.get()
    return any(event.user_id == obj.user_id for obj in cfg.super if event.platform == obj.platform)


# endregion