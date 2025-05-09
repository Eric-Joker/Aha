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
from asyncio import create_task

from regex import Match

from config import cfg
from ncatbot.core import At, MessageChain
from ncatbot.core.message import GroupMessage
from ncatbot.core.notice import NoticeMessage
from ncatbot.core.request import Request
from services.ncatbot import bot
from utils import PM, And, Or, on_message, on_notice, on_request, rm_schedules_by_meta, sec2str, str2sec
from utils.api import at_or_int, get_nickname, set_group_add_request

from .managing_member import clean_group, clean_hub, hub_notice, kick, member_notice, member_request, verify_message
from .shutup import shutup_msg, shutup_notice

HUB = cfg.get_config("hub", 114514, comment="中转站")
WELCOME_MSG = cfg.get_config("welcome_msg", "✨验证成功~ ", comment="验证成功后发的消息。")


@on_message(rf"禁言\s*{at_or_int()}\s+(\S+)", PM.admin == True)
async def shut_up(msg: GroupMessage, match: Match):
    if (sec := str2sec(match.group(2))) is None:
        return await bot.api.post_group_msg(msg.group_id, "无法识别为时间段", reply=msg.message_id)

    user_id = int(match.group(1))
    await bot.api.post_group_msg(
        msg.group_id,
        f"已将 {await get_nickname(user_id)} 从{await shutup_msg(user_id, sec)}个群里{f"禁言{sec2str(sec)}" if sec else "解禁"}。",
        reply=msg.message_id,
    )


@on_message(rf"取消黑名单\s*{at_or_int()}", PM.admin == True)
async def cancel_blacklist(msg: GroupMessage, match: Match):
    await bot.api.post_group_msg(
        msg.group_id,
        f"已取消 {await get_nickname(user_id := int(match.group(1)))} 从{await kick(user_id, is_ban := (m := match.group(1)) == "黑" or m == "ban")}个群里踢{"黑" if is_ban else "出"}。",
        reply=msg.message_id,
    )


@on_message(Or(And(rf"踢([出黑])\s*{at_or_int()}", PM.admin == True), rf"(kick|ban)\s*{at_or_int()}") & (PM.admin == True))
async def kick(msg: GroupMessage, match: Match):
    await bot.api.post_group_msg(
        msg.group_id,
        f"已将 {await get_nickname(user_id := int(match.group(2)))} 从{await kick(user_id, is_ban := (m := match.group(1)) == "黑" or m == "ban")}个群里踢{"黑" if is_ban else "出"}。",
        reply=msg.message_id,
    )


@on_notice("group_increase")
async def start_verify(msg: NoticeMessage):
    create_task(shutup_notice(msg.user_id, msg.group_id))
    if code := await member_notice(msg.user_id, msg.group_id):
        await bot.api.post_group_msg(
            msg.group_id,
            rtf=MessageChain(
                [
                    At(msg.user_id),
                    f"\n📢请在5分钟内发送【{code}】4位验证码以验证不是人机\n⚠️ 验证成功前会撤回你的所有消息，感谢配合！",
                ]
            ),
        )


@on_message(PM.validated == False, PM.limit == False)
async def verify(msg: GroupMessage, _):
    result = await verify_message(msg.raw_message, msg.user_id, msg.group_id)
    if result:
        return await bot.api.post_group_msg(msg.group_id, WELCOME_MSG, reply=msg.message_id)
    elif result is False:
        await bot.api.delete_msg(msg.message_id)


@on_notice("group_increase", PM.groups == HUB, (PM.validated == False) | (PM.validated == True))
async def hub(msg: NoticeMessage):
    create_task(hub_notice(msg.user_id))
    await bot.api.post_group_msg(
        HUB,
        rtf=MessageChain(
            [
                At(msg.user_id),
                "\n" + "\n".join([f"{len(cfg.action_groups)-i}群：{num}" for i, num in enumerate(cfg.action_groups)]),
            ]
        ),
    )


@on_notice("group_decrease", PM.groups == HUB)
async def group_decrease(msg: NoticeMessage):
    await rm_schedules_by_meta({"tag": "verify", "user_id": msg.user_id}, msg.group_id)


@on_request("group", "add")
async def group_request(msg: Request):
    await set_group_add_request(msg.flag, *await member_request(msg.user_id, msg.comment))


@on_message(r"清理中转[站群]?|中转[站群]?清人", PM.admin == True)
async def hub(msg: GroupMessage, _):
    create_task(clean_hub())
    await bot.api.post_group_msg(msg.group_id, "正在清人", reply=msg.message_id)


@on_message(r"(强制)(?:清人|清理不活跃(?:成员)?)", PM.admin == True, PM.prefix == True)
async def clean(msg: GroupMessage, match: Match):
    group, user = await clean_group(match.group(1))
    await bot.api.post_group_msg(msg.group_id, f"正在从{group}个群踢出{user}人", reply=msg.message_id)
