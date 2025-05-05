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
from sys import exit
from traceback import format_exc

from apscheduler._converters import as_aware_datetime
from apscheduler.triggers.date import DateTrigger
from attrs import define, field, validators

from services.apscheduler import scheduler

from config import cfg


@define
class TimeTrigger(DateTrigger):
    """Triggers once after the specified number of seconds.

    :param seconds: the number of seconds to wait before triggering
    """

    seconds: int = field(converter=int)
    run_time: datetime = field(init=False, converter=as_aware_datetime, validator=validators.instance_of(datetime))

    @run_time.default
    def _default_run_time(self) -> datetime:
        return datetime.now() + timedelta(seconds=self.seconds)


async def stat_schedules_by_meta(meta: dict, group_id=None):
    from services.ncatbot import bot

    schedules = []
    try:
        for schedule in await scheduler.get_schedules():
            if schedule.metadata == meta:
                schedules.append(schedule.id)
        return schedules
    except:
        if group_id:
            await bot.api.post_group_msg(group_id, "出现严重错误，已通知群主，机器人关闭。")
        await bot.api.post_private_msg(cfg.super[0], f"删除定时任务出现严重错误：\n{format_exc()}")
        exit()


async def rm_schedules_by_meta(meta: dict, group_id=None):
    for schedule in (schedules := await stat_schedules_by_meta(meta, group_id)):
        await scheduler.remove_schedule(schedule)
    return len(schedules)
