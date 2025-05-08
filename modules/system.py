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
from datetime import datetime, timedelta

from apscheduler.triggers.date import DateTrigger
from regex import Match

from config import cfg
from ncatbot.core.message import GroupMessage
from ncatbot.core.request import Request
from services.apscheduler import scheduler
from services.ncatbot import bot
from utils import (
    PM,
    And,
    Or,
    cachers,
    decimal_to_str,
    evaluate,
    menu_commands,
    on_message,
    on_request,
    process_message,
    rm_schedules_by_meta,
    stat_schedules_by_meta,
    str2sec,
)
from utils.api import at_or_int_diff, get_card_by_search, is_admin

from .money import adjust_money, inquiry_money


@on_message(Or(And(r"help|帮助|功能|指令", PM.prefix == True), "菜单"))  # 懒得写不用正则的精准匹配了，有需要 call Er1c
async def help(msg: GroupMessage, _):
    available_commands = {}
    for command, expr, desc in menu_commands:
        if await evaluate(msg, expr):
            available_commands[command] = desc

    commands = [f"{cmd}{f' - {desc}' if isinstance(desc, str) else ''}" for cmd, desc in available_commands.items()]
    commands.sort(key=lambda x: (-len(x), x))
    await bot.api.post_group_msg(
        msg.group_id,
        "\n".join(("已有功能：", *commands, f"发送{cfg.message_prefix}上述功能获取详细信息")),
        reply=msg.message_id,
    )


@on_message(rf"(触发\s*{at_or_int_diff()}\s+)\S+[\s\S]*", PM.super == True)
async def trigger(msg: GroupMessage, match: Match):
    msg.user_id = int(match.group(3))

    user_info = await get_card_by_search(msg.user_id, msg.group_id, True)
    msg.sender.card, msg.sender.nickname = user_info
    msg.sender.user_id = msg.user_id
    msg.raw_message = msg.raw_message.removeprefix(match.group(1))
    if match.group(2):
        del msg.message[:2]
    if text := msg.message[0]["data"].get("text"):
        msg.message[0]["data"]["text"] = text.removeprefix(match.group(1))

    await process_message(msg, True)


@on_message("预约", PM.prefix == True, registered_menu={"预约": "定时触发机器人指令"})
async def aps_trigger_main(msg: GroupMessage, _):
    await bot.api.post_group_msg(
        msg.group_id,
        "[预约/延迟/延时(触发) 时间段 指令]\n[取消预约] - 取消所有预约，返还一半能量\n\n消耗1点能量，每存在1个预约多消耗1点，定时触发机器人指令\n温馨提示：\n- 尽管设定的指令实际上没有任何效果，能量也不返还\n- 每个用户1分钟内最多触发3次指令，超过的会被丢弃，能量不返还",
        reply=msg.message_id,
    )


@on_message(r"((?:延迟|延时|预约)(?:触发)?\s*(\S+)\s+)(\S+[\s\S]*)")
async def aps_trigger(msg: GroupMessage, match: Match):
    if (sec := str2sec(match.group(2))) is None:
        return await bot.api.post_group_msg(msg.group_id, "无法识别为时间段", reply=msg.message_id)

    points = len(await stat_schedules_by_meta((metadata := {"user_id": msg.user_id, "tag": "trigger"}), msg.group_id)) + 1
    if not await is_admin(msg.group_id, msg.user_id):
        if (user_point := await inquiry_money(msg.user_id)) < points:
            return await bot.api.post_group_msg(
                msg.group_id, f"余额不足，需要{points}点能量，你当前有{decimal_to_str(user_point)}点。", reply=msg.message_id
            )
        else:
            await adjust_money(msg.user_id, -1)

    msg.raw_message = msg.raw_message.removeprefix(match.group(1))
    msg.message[0]["data"]["text"] = msg.message[0]["data"]["text"].removeprefix(match.group(1))
    date = datetime.now() + timedelta(seconds=sec)

    await scheduler.add_schedule(process_message, DateTrigger(date), args=(msg, True), metadata=metadata)
    await bot.api.post_group_msg(
        msg.group_id,
        f"消耗{points}点能量，将在{date.strftime("%Y年%m月%d日 %H:%M:%S")}触发“{match.group(3)}”",
        reply=msg.message_id,
    )


@on_message("取消预约")
async def cannel_trigger(msg: GroupMessage, _):
    count = await rm_schedules_by_meta({"user_id": msg.user_id, "tag": "trigger"}, msg.group_id)
    await adjust_money(msg.user_id, (point := count * (count + 1) / 4))
    await bot.api.post_group_msg(msg.group_id, f"已取消{count}个预约，返还{decimal_to_str(point)}点能量", reply=msg.message_id)


@on_request("group", "invite")
async def group_invite(msg: Request):
    if msg.user_id in cfg.super:
        return await bot.api.set_group_add_request(msg.flag, True)
    await bot.api.set_group_add_request(msg.flag, False)


@on_request("friend")
async def friend_request(msg: Request):
    await bot.api.set_friend_add_request(msg.flag, True)


@on_message(r"清理缓存", PM.super == True, PM.prefix == True)
async def clear_cache(msg: GroupMessage, _):
    for c in cachers:
        c.clear()
    await bot.api.post_group_msg(msg.group_id, "已清理。", reply=msg.message_id)
