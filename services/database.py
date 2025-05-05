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
import os
import sys

import regex as re
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.declarative import DeclarativeMeta, declarative_base
from sqlalchemy.orm import declarative_base

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from config import cfg

IS_MODULE_PATTERN = re.compile(r"^[^.]*modules[^.]*\..+")


class CustomDeclarativeMeta(DeclarativeMeta):
    def __new__(cls, name, bases, namespace, **kwargs):
        new_class = super().__new__(cls, name, bases, namespace, **kwargs)

        if "dbBase" in globals() and IS_MODULE_PATTERN.match((module := sys.modules[new_class.__module__]).__name__):
            rel_path: str = os.path.relpath(
                os.path.abspath(module.__file__), os.path.dirname(os.path.abspath(sys.modules["__main__"].__file__))
            )
            if not any(comp in {"database", "database.py"} for comp in rel_path.split(os.sep)[1:]):
                raise RuntimeError(f"Class '{name}' in module '{rel_path}' must be in a '*modules*.**.database'.")

        return new_class


db_engine = create_async_engine(cfg.database)
dbBase: DeclarativeMeta = declarative_base(metaclass=CustomDeclarativeMeta)
db_session_factory = async_sessionmaker(bind=db_engine)

alembic_cfg = Config("alembic.ini")
alembic_cfg.set_main_option("script_location", "alembic")


async def db_init():
    if check_migrations_needed():
        print("检测到数据库模型更改，正在迁移。")
        auto_generate_migrations()
        command.upgrade(alembic_cfg, "head")
    async with db_engine.begin() as conn:
        # await conn.run_sync(dbBase.metadata.create_all)
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA synchronous=NORMAL"))


def auto_generate_migrations():
    try:
        command.revision(alembic_cfg, autogenerate=True, message="auto_generated_migration")
    except Exception as e:
        if "Target database is not up to date" in str(e):
            print("存在未应用的迁移版本，请先执行 `alembic upgrade head`。")
        else:
            print(f"生成迁移脚本失败: {e}")
        raise


def check_migrations_needed():
    import services.apscheduler as sa

    with (engine := create_engine(cfg.alembic)).begin() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), [dbBase.metadata, sa.data_store.get_table_definitions()])

    engine.dispose()
    return diff
