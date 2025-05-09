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
from decimal import Decimal

from regex import Match

from config import cfg
from ncatbot.core import MessageChain, GroupMessage
from services.ncatbot import bot
from utils import PM, on_message, round_decimal

from ..money import adjust_money, inquiry_money
from .repeat import add_repeat, cancel_repeat, is_repeat

PRICE = Decimal(cfg.get_config("price", "0.1", comment="每次复读消耗的点数。"))


@on_message("复读", PM.prefix == True, registered_menu={"复读": "复读姬"})
async def rp(msg: GroupMessage, _):
    await bot.api.post_group_msg(
        msg.group_id,
        f"[开启/关闭复读] - 复读之后的所有消息\n[{cfg.message_prefix}复读 消息]\n\n一个群内只能同时存在3个开启复读的用户，开启超过一分钟后可以被顶替\n每次复读消耗{round_decimal(PRICE)}点能量\n温馨提示：每个用户每分钟只能触发3次指令",
        reply=msg.message_id,
    )


@on_message(PM.limit == False)
async def feature(msg: GroupMessage, _):
    if (
        msg.raw_message != "开启复读"
        and msg.raw_message != "关闭复读"
        and not msg.raw_message.startswith("复读")
        and await is_repeat(msg.user_id, msg.group_id)
    ):
        if await inquiry_money(msg.user_id) < PRICE:
            await msg.reply("余额不足，关闭复读。")
            return await cancel_repeat(msg.user_id, msg.group_id)
        await adjust_money(msg.user_id, -PRICE)
        await bot.api.post_group_msg(msg.group_id, rtf=MessageChain([msg.raw_message]))


@on_message("开启复读")
async def start_repeat(msg: GroupMessage, _):
    if await add_repeat(msg.user_id, msg.group_id):
        await bot.api.post_group_msg(msg.group_id, "已开启", reply=msg.message_id)
    elif await inquiry_money(msg.user_id) < PRICE * 2:
        return await bot.api.post_group_msg(msg.group_id, "能量过少", reply=msg.message_id)


@on_message("关闭复读")
async def stop_repeat(msg: GroupMessage, _):
    await bot.api.post_group_msg(
        msg.group_id,
        "已关闭" if await cancel_repeat(msg.user_id, msg.group_id) else "无法关闭未开启的事物",
        reply=msg.message_id,
    )


@on_message(r"复读\s*([\s\S]+)", PM.prefix == True)
async def single(msg: GroupMessage, match: Match):
    if msg.message[0]["type"] == "text":
        if await inquiry_money(msg.user_id) < PRICE:
            await bot.api.post_group_msg(msg.group_id, "余额不足。", reply=msg.message_id)
        await adjust_money(msg.user_id, -PRICE)
        await bot.api.post_group_msg(msg.group_id, rtf=MessageChain([match.group(1)]))
