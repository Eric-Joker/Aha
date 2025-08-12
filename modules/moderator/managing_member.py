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
from asyncio import Semaphore, create_task, gather
from datetime import datetime, timedelta
from logging import getLogger
from random import Random

from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import delete, func, insert, select

from config import cfg
from services.apscheduler import scheduler
from services.database import db_session_factory
from services.ncatbot import bot
from utils import TimeTrigger, on_start, rm_schedules_by_meta
from utils.api import GroupMemberInfo, get_group_member_list, get_level_by_search, set_group_kick

from .database import BlackList, HubIncrease, Verify

logger = getLogger(__name__)

LIMIT_LEVEL = cfg.get_config("limit_level", 0, comment="只有用户等级大于此值时才会允许加群。")
CONNOT_GET_LEVEL = cfg.get_config(
    "connot_get_level", "无法获取QQ等级，请在资料卡展示等级且加中转群%s", comment="无法获取用户等级时的拒绝原因。"
)
LOW_LEVEL = cfg.get_config("low_level", "QQ等级过低", comment="用户等级过低时的拒绝原因。")
INACTIVE_LIMIT = cfg.get_config("inactive_limit", 9999, comment="清理不活跃成员的绝对值阈值，达到阈值后才会触发清理。")
KICK_LEVEL = cfg.get_config("kick_level", 10, comment="用户的群聊等级小于此值时可能会被踢出群。")


async def member_request(user_id, comment: str):
    if "管理员" in comment:
        reason = "很遗憾，你的加群原因触发了关键字"
        # logger.info(f"拒绝{user_id}加群，因为{reason}")
        return False, reason
    async with db_session_factory() as session:
        if await session.scalar(select(select(BlackList).filter(BlackList.user_id == user_id).exists())):
            # logger.info(f"拒绝{user_id}加群，因为黑名单")
            return False, None
    if not (level := await get_level_by_search(user_id)):
        reason = CONNOT_GET_LEVEL % cfg.hub
        # logger.info(f"拒绝{user_id}加群，因为{reason}")
        return False, reason
    if level <= LIMIT_LEVEL:
        reason = LOW_LEVEL
        # logger.info(f"拒绝{user_id}加群，因为{reason}")
        return False, reason
    return True, None


async def kick(user_id, is_ban):
    if is_ban:
        async with db_session_factory() as session:
            await session.execute(insert(BlackList).values(user_id=user_id).prefix_with("OR REPLACE"))
            await session.commit()
    success = 0
    for gid in cfg.action_groups:
        success += await set_group_kick(gid, user_id, is_ban)
    return success


async def member_notice(user_id, group_id):
    async with db_session_factory() as session:
        if await session.scalar(select(Verify.is_validated).filter(Verify.user_id == user_id)):
            return
        code = Random(user_id).randint(1000, 9999)
        await session.execute(insert(Verify).values(user_id=user_id, code=code).prefix_with("OR REPLACE"))
        await session.commit()
    await scheduler.add_schedule(
        set_group_kick, TimeTrigger(300), args=(group_id, user_id), metadata={"user_id": user_id, "tag": "verify"}
    )
    return code


async def verify_message(message: str, user_id, group_id):
    async with db_session_factory() as session:
        if (
            len(message) == 4
            and message.isdigit()
            and message.isascii()
            and (result := await session.get(Verify, user_id))
            and int(message) == result.code
        ):
            await rm_schedules_by_meta({"tag": "verify", "user_id": user_id}, group_id)
            create_task(set_group_kick(cfg.hub, user_id))
            create_task(clean_group())
            result.is_validated = True
            await session.commit()
            return True
        if (result := await session.get(Verify, user_id)) and not result.is_validated:
            if result.times >= 4:
                create_task(rm_schedules_by_meta({"tag": "verify", "user_id": user_id}, group_id))
                create_task(bot.api.set_group_kick(group_id, user_id))
            result.times += 1
            await session.commit()
            return False


async def hub_notice(user_id):
    async with db_session_factory() as session:
        await session.execute(insert(HubIncrease).values(user_id=user_id, time=datetime.now()).prefix_with("OR REPLACE"))
        await session.commit()


async def clean_hub():
    user_ids = {
        member.user_id
        for member in (await get_group_member_list(cfg.hub))
        if member.role == "member" and member.user_id not in cfg.super
    }

    async with db_session_factory() as session:
        # 批量查询普通用户的最后记录时间
        result = await session.execute(
            select(HubIncrease.user_id, func.max(HubIncrease.time).label("last_time"))
            .where(HubIncrease.user_id.in_(user_ids))
            .group_by(HubIncrease.user_id)
        )

        expired_users = {
            user_id for user_id, last_time in dict(result.all()).items() if (datetime.now() - last_time) >= timedelta(days=1)
        }
        if expired_users:
            await session.execute(delete(HubIncrease).where(HubIncrease.user_id.in_(expired_users)))
            await session.commit()

    semaphore = Semaphore(1)
    async with semaphore:
        for uid in expired_users:
            create_task(bot.api.set_group_kick(cfg.hub, uid))


@on_start
async def add_clean_hub_schedule():
    await scheduler.add_schedule(clean_hub, CronTrigger(hour=0, minute=0, second=0), id="clean_hub")


async def clean_group(force=False):
    last_month = ((now := datetime.now().replace(microsecond=0)).replace(day=1) - timedelta(days=1)).replace(day=now.day)
    member_lists = await gather(*(get_group_member_list(gid, True) for gid in cfg.action_groups), return_exceptions=True)

    group = 0
    user = 0
    semaphore = Semaphore(1)

    async def process_group(gid, members: list[GroupMemberInfo]):
        nonlocal group, user
        if isinstance(members, Exception):
            return

        if force or len(members) >= INACTIVE_LIMIT:
            group += 1
            create_task(bot.api.post_group_msg(gid, "开始清人"))

            admin_set = {m.user_id for m in members if m.role != "member"}
            for member in members:
                if (
                    member.user_id not in admin_set
                    and datetime.fromtimestamp(member.last_sent_time) <= last_month
                    and int(member.level) < KICK_LEVEL
                ):
                    user += 1
                    async with semaphore:
                        create_task(bot.api.set_group_kick(gid, member.user_id))

    await gather(*(process_group(gid, members) for gid, members in zip(cfg.action_groups, member_lists)))
    return group, user
