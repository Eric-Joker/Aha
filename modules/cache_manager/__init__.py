from collections.abc import Callable

from pympler import asizeof
from core.cache import cachers, clear_all_cache
from core.expr import PM
from core.i18n import _
from core.dispatcher import on_message
from models.api import Message

__all__ = ()


@on_message(_("clear_cache"), PM.super == True, PM.prefix == True)
async def clear_cache(event: Message, localizer):
    clear_all_cache()
    await event.reply(localizer("clear_cache.success"))


@on_message(_("cache_status"), PM.super == True, PM.prefix == True)
async def cache_status(event: Message, localizer: Callable[[str], str]):
    #await event.reply(localizer("cache_used") % sum(asizeof.asizeof(c) for c in cachers))
    await event.reply("\n".join(f"{c.__class__.__name__}: {asizeof.asizeof(c)}" for c in cachers))
