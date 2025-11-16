import gzip
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from re import compile
from shutil import which
from subprocess import run

import sqlalchemy.sql.schema
from sqlalchemy import BINARY, NUMERIC, create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.declarative import DeclarativeMeta, declarative_base
from sqlalchemy.orm import DeclarativeBase

from core.arg_parser import parser
from models.exc import DatabaseBackupError
from utils.misc import AHA_MODULE_PATTERN, caller_aha_module

from .config import cfg
from .i18n import _

__all__ = ("db_engine", "dbBase", "metadata", "db_sessionmaker")

MODULE_AUTHOR_PATTERN = compile(r"^modules\.([^.]+)")
DATABASEPATHS = frozenset(("database", "database.py"))

database_initialized = False


class CustomDeclarativeMeta(DeclarativeMeta):
    def __init__(cls, classname, bases, dict_):
        if match := MODULE_AUTHOR_PATTERN.match((module := sys.modules[cls.__module__]).__name__):
            """
            rel_path: str = os.path.relpath(
                os.path.abspath(module.__file__), os.path.dirname(os.path.abspath(sys.modules["modules"].__file__))
            )
            if all(comp not in DATABASEPATHS for comp in rel_path.split(os.sep)):
                raise RuntimeError(_("database.path_error") & {"class": classname, "module": module.__name__})
            """
            from modules import SYSTEM_MODULES

            if (module := match[1]) not in SYSTEM_MODULES:
                cls.__tablename__ = f"{cls.__tablename__}__{module}"

        super().__init__(classname, bases, dict_)


db_engine = create_async_engine(cfg.database["uri"])
dbBase: DeclarativeBase = declarative_base(metaclass=CustomDeclarativeMeta)
metadata = dbBase.metadata
db_sessionmaker = async_sessionmaker(bind=db_engine)

_discard_log = {"Context impl SQLiteImpl.", "Will assume non-transactional DDL."}
logging.getLogger("alembic.runtime.migration").addFilter(
    lambda record: record.levelno != logging.INFO or record.getMessage() not in _discard_log
)
logging.getLogger("alembic.runtime.plugins").addFilter(
    lambda record: record.levelno != logging.INFO or not record.getMessage().startswith("set")
)

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.util.sqla_compat import _table_for_constraint

alembic_cfg = Config("alembic.ini")
alembic_cfg.set_main_option("script_location", "alembic")
alembic_cfg.set_main_option("sqlalchemy.url", cfg.database["green"])

_logger = logging.getLogger("AHA (database)")


def db_init():
    global database_initialized

    from services.apscheduler import sched

    with create_engine(cfg.database["green"]).begin() as conn:
        dbBase.metadata.create_all(conn)
        sched.data_store.get_table_definitions().create_all(conn)
        if db_engine.dialect.name == "sqlite":
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA synchronous=NORMAL"))

    compare_loggers = (
        logging.getLogger("alembic.autogenerate.compare"),
        logging.getLogger("alembic.autogenerate.compare.tables"),
        logging.getLogger("alembic.autogenerate.compare.constraints"),
    )
    for logger in compare_loggers:
        logger.filters = [lambda _: False]
    if check_migrations_needed():
        for logger in compare_loggers:
            logger.filters = []
        _logger.warning(_("database.detected_changes"))

        if not parser.no_db_backup:
            backup_database()
        try:
            command.revision(alembic_cfg, autogenerate=True, message="aha_auto_generated")
        except Exception as e:
            if "Target database is not up to date" in str(e):
                _logger.error(_("database.gen_version.not_up_to_date"))
            else:
                _logger.error(_("database.gen_version.error") % e)
            raise
        command.upgrade(alembic_cfg, "head")

    database_initialized = True

    for name in {name for name in sys.modules if name == "alembic" or name.startswith("alembic.")}:
        del sys.modules[name]


def check_migrations_needed():
    from services.apscheduler import sched

    with (engine := create_engine(cfg.database["green"])).begin() as conn:
        diff = compare_metadata(
            MigrationContext.configure(conn, opts={"compare_type": compare_type}),
            [dbBase.metadata, sched.data_store.get_table_definitions()],
        )
    engine.dispose()

    # 忽略元数据中不存在表的更改
    for i in range(len(diff) - 1, -1, -1):
        if (j := diff[i])[0] == "remove_table":
            tables_to_exclude.add(j[1].name)
            del diff[i]

    for i in range(len(diff) - 1, -1, -1):
        match (j := diff[i])[0]:
            case "remove_index":
                if j[1].table.name in tables_to_exclude:
                    del diff[i]
            case "remove_constraint" | "remove_fk":
                if _table_for_constraint(j[1]).name in tables_to_exclude:
                    del diff[i]
            case "remove_table_comment":
                if j[1].name in tables_to_exclude:
                    del diff[i]

    return diff


# region 用于版本生成
tables_to_exclude = set()


def compare_type(_, __, ___, inspected_type, metadata_type):
    if isinstance(inspected_type, NUMERIC) and isinstance(metadata_type, BINARY):
        return False

    return None


def include_object(obj, name, type_, reflected, _):
    match type_:
        case "table":
            return not (reflected and name in tables_to_exclude)
        case "index":
            return obj.table.name not in tables_to_exclude
        case "unique_constraint" | "foreign_key_constraint":
            return _table_for_constraint(obj).name not in tables_to_exclude
    return True


# endregion
def backup_database():
    try:
        if "sqlite" in (url := make_url(cfg.database["green"])).drivername:
            if not url.database or url.database == ":memory:":
                _logger.warning(_("database.backup.not_supported"))
            _logger.info(_("database.backup.start"))
            (backup_dir := Path(cfg.database["backup_dir"])).mkdir(parents=True, exist_ok=True)
            with open(url.database, "rb") as f_in:
                with gzip.open(
                    backup_dir
                    / f"{os.path.splitext(os.path.basename(url.database))[0]}_{datetime.now().strftime('%Y%m%d_%H%M%S%f')[:-3]}.db.gz",
                    "wb",
                ) as f_out:
                    f_out.write(f_in.read())
        elif "postgresql" in url.drivername:
            if (pg_dump := which("pg_dump")) is None:
                raise DatabaseBackupError(_("database.backup.pg_dump404"))
            _logger.info(_("database.backup.start"))
            (backup_dir := Path(cfg.database["backup_dir"])).mkdir(parents=True, exist_ok=True)
            __, sep, right = cfg.database["green"].partition("://")
            run(
                [
                    pg_dump,
                    "-d",
                    f"postgresql{sep}{right}" if sep else cfg.database["green"],
                    "-F",
                    "c",
                    "-Z 9",
                    "-j",
                    os.cpu_count(),
                    "-f",
                    cfg.database["backup_dir"],
                ],
                check=True,
            )
        else:
            _logger.warning(_("database.backup.not_supported"))
    except Exception:
        _logger.exception(_("database.backup.error"))
        sys.exit(1)


# region monkey patch
_otableinit = sqlalchemy.sql.schema.Table.__init__


def __init__(self, name, *args, **kwargs):
    if mod := caller_aha_module(pattern=AHA_MODULE_PATTERN):
        name = f"{name}__{mod}"
    _otableinit(self, name, *args, **kwargs)


sqlalchemy.sql.schema.Table.__init__ = __init__
# endregion
