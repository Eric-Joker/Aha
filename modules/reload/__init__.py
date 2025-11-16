
from asyncio import create_task

from core.api import API
from core.expr import PM
from core.i18n import _
from core.router import on_external, on_message
from models.api import Message
from utils.api import post_msg_to_supers

__all__ = ()


@on_message(PM.message == _("reload"), PM.prefix == True, PM.super == True)
async def msg_entry(event: Message, localizer):
    from .. import reload_modules

    await API.poke()
    await reload_modules()
    await event.reply(localizer("reloaded"))


@on_external("reload")
async def api_entry(data):
    from .. import reload_modules

    await reload_modules()
    create_task(post_msg_to_supers(_("reloaded")))
