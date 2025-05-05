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
from regex import Match

from ncatbot.core.message import GroupMessage
from services.ncatbot import bot
from utils import PM, on_message


@on_message(r"头衔\s+(.+)", PM.group == False)
async def title(msg: GroupMessage, match: Match):
    new_title = match.group(1).strip()
    if 0 < len(new_title) <= 12:  # QQ头衔长度限制
        await bot.api.set_group_special_title(msg.group_id, msg.user_id, new_title)
        await bot.api.post_group_msg(msg.group_id, "设置头衔:" + new_title, reply=msg.message_id)
    else:
        await bot.api.post_group_msg(msg.group_id, "头衔长度不符合要求(1-12个字符)", reply=msg.message_id)
