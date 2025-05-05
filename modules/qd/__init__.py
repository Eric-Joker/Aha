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
from utils import PM, And, on_message, Or
from utils.api import get_card_by_msg

from .qd import sign


@on_message(Or(r"q+d+|早|签到", And("sign", (PM.prefix == True))), registered_menu={"签到": None})
async def dk(msg: GroupMessage, _):
    await bot.api.post_group_msg(
        msg.group_id, "\n".join(filter(None, await sign(msg.user_id, await get_card_by_msg(msg)))), reply=msg.message_id
    )
