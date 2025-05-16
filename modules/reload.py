# Copyright (C) 2025 github.com/Eric-Joker
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
import utils.message_router as ul
from config import cfg
from ncatbot.core.message import GroupMessage
from services.ncatbot import bot
from utils import PM, on_message, queue_handler


def reload():
    ul.message_handlers.clear()
    ul.notice_handlers.clear()
    ul.queue_handlers.clear()
    ul.request_handlers.clear()
    ul.start_handlers.clear()

    if cfg.enable_fastapi:
        from fastapi_modules import reload_fastapi_modules

        reload_fastapi_modules()
    from . import reload_modules

    reload_modules()
    


@on_message("重载", PM.prefix == True, PM.super == True)
async def msg_entry(msg: GroupMessage, _):
    await bot.api.send_poke(msg.user_id, msg.group_id)
    reload()
    await bot.api.post_group_msg(msg.group_id, "已重载所有模块", reply=msg.message_id)


@queue_handler("reload")
async def api_entry(_):
    reload()
    await bot.api.post_private_msg(cfg.super[0], "已重载所有模块")
