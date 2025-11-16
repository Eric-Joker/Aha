from asyncio import create_task

from sqlalchemy import delete

import core.status
from core.api import API, SS, select_bot
from core.config import cfg
from core.database import db_sessionmaker
from core.dispatcher import on_external, on_message, on_start
from core.expr import PM
from core.i18n import _
from models.api import Message
from utils.sqlalchemy import upsert

from .database import Status

__all__ = ("reload_or_restart")


async def reload_or_restart():
    if cfg.debug:
        from .. import reload_modules

        create_task(reload_modules())
    else:
        core.status.need_reboot = True
        core.status.main_task.cancel()


@on_start
async def post_msg():
    async with db_sessionmaker() as session:
        for row in (await session.execute(delete(Status).returning(Status))).scalars().all():
            await API.send_msg(
                user_id=row.user_id,
                group_id=row.group_id,
                msg=_("reloaded"),
                reply=row.message_id,
                bot=row.bot_id or select_bot(SS.GROUP_NTH, platform=row.platform, conv_id=row.group_id),
            )
        await session.commit()


@on_message(PM.message == _("reload"), PM.prefix == True, PM.super == True)
async def msg_entry(event: Message):
    await API.poke()

    async with db_sessionmaker() as session:
        await session.execute(
            upsert(
                Status,
                user_id=event.user_id,
                group_id=event.group_id,
                message_id=event.message_id,
                platform=event.platform,
                bot_id=event.bot_id,
            )
        )
        await session.commit()
    await reload_or_restart()


@on_external("reload")
async def api_entry():
    async with db_sessionmaker() as session:
        for s in cfg.super:
            await session.execute(upsert(Status, user_id=s.user_id, platform=s.platform))
        await session.commit()
    await reload_or_restart()
