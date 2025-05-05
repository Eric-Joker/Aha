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
from time import time

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from config import cfg
from services.database import db_session_factory

from .database import Repeat


async def add_repeat(user_id, group_id):
    current_time = int(time())
    async with db_session_factory() as session:
        count = await session.scalar(select(func.count()).where(Repeat.group_id == group_id).with_for_update())
        if 0 <= count < 3:
            try:
                await session.execute(
                    insert(Repeat).values(user_id=user_id, group_id=group_id, enable_time=current_time, last_time=current_time)
                )
                await session.commit()
                return True
            except IntegrityError:
                await session.rollback()
                return None
        oldest_record = await session.scalar(
            select(Repeat).where(Repeat.group_id == group_id).order_by(Repeat.enable_time.asc()).limit(1)
        )
        if not oldest_record or current_time - oldest_record.enable_time < 60:
            await session.rollback()
            return False

        await session.execute(
            update(Repeat)
            .where(Repeat.user_id == oldest_record.user_id, Repeat.group_id == oldest_record.group_id)
            .values(user_id=user_id, enable_time=current_time, last_time=current_time)
        )
        await session.commit()
        return True


async def cancel_repeat(user_id, group_id):
    async with db_session_factory() as session:
        result = await session.execute(delete(Repeat).where(Repeat.user_id == user_id, Repeat.group_id == group_id))
        await session.commit()
        return result.rowcount > 0


async def is_repeat(user_id, group_id):
    current_time = int(time())

    async with db_session_factory() as session:
        if not (record := await session.get(Repeat, (user_id, group_id), with_for_update=True)):
            return False

        if user_id in cfg.super:
            return True
        if record.last_time >= current_time - 60:
            if record.count >= 3:
                return False
            record.count += 1
        else:
            # 新时间窗口重置计数
            record.count = 1

        record.last_time = current_time
        await session.commit()
    return True
