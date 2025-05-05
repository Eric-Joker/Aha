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
from random import randint

from regex import Match

from config import cfg
from ncatbot.core.message import GroupMessage
from services.ncatbot import bot
from utils import PM, And, Or, on_message, round_decimal, sec2str, str2sec
from utils.api import get_card_by_msg, set_group_ban

from ..money import adjust_money, inquiry_money

PRICE = Decimal(cfg.get_config("price", "5", comment="每从一个群解禁消耗的点数。"))


@on_message(Or(And(r"(?:禁言我|jy)\s*(\S+)", PM.prefix == True), r"(?:禁言我|jy)\s*(\S+)\s+(\S+)", r"随机禁言|sjjy"))
async def shutup(msg: GroupMessage, match: Match):
    num1 = str2sec(match.group(1)) if match.lastindex else 1
    num2 = str2sec(match.group(2)) if match.lastindex == 2 else num1 if match.lastindex else 60
    if not num1 or not num2:
        return await bot.api.post_group_msg(msg.group_id, f"无法识别为时间段", reply=msg.message_id)

    num1 = max(min(num1, 2591940), 1)
    num2 = max(min(num2, 2591940), 1)
    await set_group_ban(msg.group_id, msg.user_id, seconds := randint(min(num1, num2), max(num1, num2)) if num2 else num1)
    await bot.api.post_group_msg(msg.group_id, f"禁言 {await get_card_by_msg(msg)} {sec2str(seconds)}", reply=msg.message_id)


@on_message("禁言", PM.prefix == True, registered_menu={"禁言": "Shut up!"})
async def su(msg: GroupMessage, _):
    await bot.api.post_group_msg(
        msg.group_id,
        f"闭嘴！：\n🔥[随机禁言/sjjy]🔥 - 1-60s\n[禁言我/jy 时长 时长] - 随机禁言\n[{cfg.message_prefix}禁言我/jy 时长]\n\n最小1s，最大29天23时59秒，自动校正\n作死后可以加其他分群发送“解除禁言”",
        reply=msg.message_id,
    )


@on_message("解除禁言")
async def speak(msg: GroupMessage, _):
    times = 0
    for g in cfg.action_groups:
        if await inquiry_money(msg.user_id) < PRICE:
            if times == 0:
                return await bot.api.post_group_msg(msg.group_id, f"能量不足{PRICE}点", reply=msg.message_id)
        if await set_group_ban(g, msg.user_id):
            await adjust_money(msg.user_id, -PRICE)
            times += 1
    await bot.api.post_group_msg(msg.group_id, f"消耗{times * PRICE}能量，解除{times}个群的禁言", reply=msg.message_id)
