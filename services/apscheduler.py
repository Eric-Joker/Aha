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
import apscheduler

from services.database import db_engine

if hasattr(apscheduler, "__version__"):
    raise ImportError("apscheduler 需要 4.0 或以上版本。")

from apscheduler import AsyncScheduler
from apscheduler.datastores.sqlalchemy import SQLAlchemyDataStore

data_store = SQLAlchemyDataStore(db_engine)
scheduler = AsyncScheduler(data_store, cleanup_interval=None)


async def cleanup_cb(*_):
    await scheduler.cleanup()


def scheduler_init():
    scheduler.subscribe(cleanup_cb, {apscheduler.JobReleased}, one_shot=False)
