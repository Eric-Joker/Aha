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

from ncatbot.core.message import GroupMessage
from regex import Match
from sqlalchemy import func, insert, select, update

from config import cfg
from services.database import db_session_factory
from services.ncatbot import bot
from utils import PM, And, Or, decimal_to_str, on_message, round_decimal
from utils.api import at_or_int, get_card_by_search, get_group_member_list

from .database import Money

HANDLING_FEE_RATIO = Decimal(cfg.get_config("handling_fee", "0.01", comment="转账手续费"))


async def adjust_money(user_id, points: int | Decimal):
    async with db_session_factory() as session:
        result = await session.execute(update(Money).where(Money.user_id == user_id).values(points=Money.points + points))
        if result.rowcount == 0:
            await session.execute(insert(Money).values(user_id=user_id, points=points))
        await session.commit()
    return points


async def inquiry_money(user_id) -> Decimal:
    async with db_session_factory() as session:
        return (await session.scalar(select(Money.points).filter(Money.user_id == user_id))) or Decimal(0)


@on_message(And("(能量|积分|货币)系统", PM.prefix == True), registered_menu={"能量系统": None})
async def money_system(msg: GroupMessage, _):
    await bot.api.post_group_msg(
        msg.group_id,
        f"能量系统：\n[{cfg.message_prefix}能量守恒] - 查询全体用户能量总量\n[{cfg.message_prefix}(能量)查询] - 查询个人能量数量\n[(能量)转账 @或QQ号 数量]",
        reply=msg.message_id,
    )


@on_message(r"能量守恒", PM.prefix == True)
async def conservation_handler(msg: GroupMessage, _):
    async with db_session_factory() as session:
        result = await session.execute(select(func.sum(Money.points)).where(Money.user_id.notin_(cfg.super)))
    await bot.api.post_group_msg(
        msg.group_id,
        f"📊 当前时空总能量：{decimal_to_str(round_decimal(result.scalar())) or 0}点（守恒率99.{randint(80,99)}%）",
        reply=msg.message_id,
    )


@on_message(Or(r"(?:能量|积分)(?:查询)?", r"查询") & (PM.prefix == True))
async def query_points(msg: GroupMessage, _):
    await bot.api.post_group_msg(
        msg.group_id,
        f"🔋当前能量储备：{decimal_to_str(round_decimal(await inquiry_money(msg.user_id)))} 点",
        reply=msg.message_id,
    )


@on_message(Or(rf"(?:能量|积分)转(?:移|账)\s*{at_or_int()}\s+(\d+\.\d+)", rf"转(?:移|账)\s*{at_or_int()}\s+(\d+)"))
async def transfer_handler(msg: GroupMessage, match: Match):
    if await inquiry_money(msg.user_id) <= HANDLING_FEE_RATIO:
        return await bot.api.post_group_msg(msg.group_id, "⚠️ 能量不足以转出", reply=msg.message_id)
    if (receiver_id := int(match.group(1))) not in {i.user_id for i in (await get_group_member_list(msg.group_id, True))}:
        return await bot.api.post_group_msg(msg.group_id, "⚠️ 目标用户不是本群成员", reply=msg.message_id)

    points = Decimal(match.group(2))

    # 手续费
    tax = max(HANDLING_FEE_RATIO, round_decimal(HANDLING_FEE_RATIO * points, abs(HANDLING_FEE_RATIO.as_tuple().exponent)))
    actual_points = points - tax

    # 执行转移
    await adjust_money(msg.user_id, -points)
    await adjust_money(receiver_id, actual_points)

    if receiver_id == msg.self_id:
        return await bot.api.post_group_msg(msg.group_id, f"⚫已将 {match.group(2)} 点能量投入黑洞！", reply=msg.message_id)
    await bot.api.post_group_msg(
        msg.group_id,
        f"⚡能量转移成功！\n- 转出：{match.group(2)}点\n- 手续费：{decimal_to_str(tax)}点\n- 实际到账：{decimal_to_str(actual_points)}点",
        reply=msg.message_id,
    )


@on_message(rf"(?:能量|积分)?调整\s*{at_or_int()}\s+(\d+\.?\d*)", PM.super == True)
async def adjust_points(msg: GroupMessage, match: Match):
    await adjust_money((user_id := int(match.group(1))), float(match.group(2)))
    await bot.api.post_group_msg(
        msg.group_id,
        f"已为 {await get_card_by_search(user_id, msg.group_id)} 添加 {match.group(2)} 点",
        reply=msg.message_id,
    )


@on_message(rf"(?:能量|积分)?设置\s*{at_or_int()}\s+(\d+\.?\d*)", PM.super == True)
async def set_points(msg: GroupMessage, match: Match):
    points = float(match.group(2))
    user_id = int(match.group(1))
    async with db_session_factory() as session:
        await session.execute(insert(Money).values(user_id=user_id, points=points).prefix_with("OR REPLACE"))
        await session.commit()

    await bot.api.post_group_msg(
        msg.group_id,
        f"已将 {await get_card_by_search(user_id, msg.group_id)} 的积分设置为 {match.group(2)} 点",
        reply=msg.message_id,
    )
