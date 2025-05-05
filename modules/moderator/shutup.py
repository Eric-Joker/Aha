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
from sqlalchemy import insert, select

from config import cfg
from services.apscheduler import scheduler
from services.database import db_session_factory
from utils.api import set_group_ban

from .database import Shutup


async def shutup_msg(user_id, duration: int):
    initial_ban = max(min(duration, 2591940), 0)
    remain = duration - initial_ban if duration > 2591940 else 0

    if initial_ban > 0:
        async with db_session_factory() as session:
            timestamp = datetime.now() + timedelta(seconds=initial_ban)
            await session.execute(
                insert(Shutup).values(user_id=user_id, timestamp=timestamp, remain=remain).prefix_with("OR REPLACE"),
            )
            await session.commit()

    # 执行首次禁言
    success = 0
    for gid in cfg.action_groups:
        success += await set_group_ban(gid, user_id, initial_ban)

    # 安排续期任务
    if remain > 0:
        await scheduler.add_schedule(_renew_task, DateTrigger(timestamp - timedelta(seconds=60)), args=(user_id,))

    return success


async def _renew_task(user_id):
    async with db_session_factory() as session:
        if not (record := await session.get(Shutup, user_id)) or record.remain <= 0:
            return

        record.timestamp = datetime.now() + timedelta(seconds=(ban_seconds := min(record.remain, 2591940)))
        record.remain -= ban_seconds
        await session.commit()

        for gid in cfg.action_groups:
            await set_group_ban(gid, user_id, ban_seconds)

        if record.remain > 0:
            await scheduler.add_schedule(_renew_task, DateTrigger(record.timestamp - timedelta(seconds=60)), args=(user_id))


async def shutup_notice(user_id, group_id):
    async with db_session_factory() as session:
        row: datetime = await session.scalar(select(Shutup.timestamp).filter(Shutup.user_id == user_id))
        if row and (remain := (row - datetime.now()).total_seconds()) > 0:
            await set_group_ban(group_id, user_id, remain)
