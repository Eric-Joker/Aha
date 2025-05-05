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
from ncatbot.core.message import GroupMessage
from services.ncatbot import bot
from utils import PM, on_message


@on_message("亲密度", PM.prefix == True)
async def close(msg: GroupMessage, _):
    await bot.api.post_group_msg(msg.group_id, "亲密度查询：https://h5.qzone.qq.com/close/rank")
