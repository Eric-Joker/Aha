from functools import partial
from re import Match
from time import time

from core.api_service import platform_bot_map
from core.config import cfg
from core.expr import Pmessage, Pprefix, Psuper
from core.i18n import _
from core.identity import map_user
from core.router import on_message
from models.api import Message
from models.core import User
from utils.api import at_or_str, is_super

linking: dict = {}


@on_message(_("link"), Pprefix == True, register_help={_("link"): _("desc")})
async def mapper(event: Message, localizer):
    await event.reply(
        (localizer("help_admin") if await is_super() else localizer("help"))
        % {"prefix": cfg.message_prefix, "platforms": "\n  ".join(platform_bot_map)}
    )


@on_message(_("command") % (a := at_or_str(), a), Pprefix == True)
async def linker(event: Message, match: Match, localizer):
    if uid := match[2]:
        if (platform := match[1]) not in platform_bot_map:
            return await event.reply(localizer("unknown_platform"))
    else:
        platform, uid = event.platform, match[1]
    if await is_super():
        if await map_user(event.platform, event.user_id, platform, uid):
            return await event.reply(localizer("linked"))
        else:
            return await event.reply(localizer("unknown_user"))
    if (t := linking.get(event.user)) and t + 300 >= time():
        return await event.reply(localizer("frequently"))

    linking[event.user] = time()
    on_message(
        Pmessage == "!y",
        Pprefix == False,
        exp=300,
        callback=partial(check_link, args=(event.platform, event.user_id, platform, uid)),
    )
    return await event.reply(_("need"))


@on_message(_("command_admin") % (a := at_or_str(), a), Pprefix == True, Psuper == True)
async def linker_admin(event: Message, match: Match, localizer):
    if (platform := match[2]) not in platform_bot_map:
        return event.reply(localizer("unknown_platform"))
    if await map_user(event.platform, match[1], platform, match[3]):
        return await event.reply(localizer("linked"))
    else:
        return await event.reply(localizer("unknown_user"))


async def check_link(event: Message, localizer, args):
    del linking[User(args[0], args[1])]
    if await map_user(*args):
        return await event.reply(localizer("linked"))
    else:
        return await event.reply(localizer("unknown_user"))
