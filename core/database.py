
import logging
import os
import sys
from re import compile

from sqlalchemy import BINARY, NUMERIC, create_engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.declarative import DeclarativeMeta, declarative_base
from sqlalchemy.orm import DeclarativeBase, declarative_base

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.util.sqla_compat import _table_for_constraint

from .config import cfg
from .i18n import _

__all__ = ("db_engine", "dbBase", "db_session_factory")

MODULE_AUTHOR_PATTERN = compile(r"^modules\.([^.]+)")
DATABASEPATHS = {"database", "database.py"}

database_initialized = False


class CustomDeclarativeMeta(DeclarativeMeta):
    def __init__(cls, classname, bases, dict_):
        if match := MODULE_AUTHOR_PATTERN.match((module := sys.modules[cls.__module__]).__name__):
            rel_path: str = os.path.relpath(
                os.path.abspath(module.__file__), os.path.dirname(os.path.abspath(sys.modules["modules"].__file__))
            )
            if all(comp not in DATABASEPATHS for comp in rel_path.split(os.sep)):
                raise RuntimeError(_("database.path_error") & {"class": classname, "module": module.__name__})
            from modules import SYSTEM_MODULES

            if (module := match[1]) not in SYSTEM_MODULES:
                cls.__tablename__ = f"{cls.__tablename__}__{module}"

        super().__init__(classname, bases, dict_)


db_engine = create_async_engine(cfg.database)
dbBase: DeclarativeBase = declarative_base(metaclass=CustomDeclarativeMeta)
db_session_factory = async_sessionmaker(bind=db_engine)

alembic_cfg = Config("alembic.ini")
alembic_cfg.set_main_option("script_location", "alembic")
alembic_cfg.set_main_option("sqlalchemy.url", cfg.green_db)

_discard_log = {"Context impl SQLiteImpl.", "Will assume non-transactional DDL."}
logging.getLogger("alembic.runtime.migration").addFilter(
    lambda record: record.levelno != logging.INFO or record.getMessage() not in _discard_log
)
_logger = logging.getLogger("AHA (database)")


def db_init():
    global database_initialized

    from services.apscheduler import scheduler

    with create_engine(cfg.green_db).begin() as conn:
        dbBase.metadata.create_all(conn)
        scheduler.data_store.get_table_definitions().create_all(conn)
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA synchronous=NORMAL"))

    (compare_logger := logging.getLogger("alembic.autogenerate.compare")).filters = [lambda _: False]
    if check_migrations_needed():
        compare_logger.filters = []
        _logger.warning(_("database.detected_changes"))

        auto_generate_migrations()
        command.upgrade(alembic_cfg, "head")

    database_initialized = True

    for name in {name for name in sys.modules if name == "alembic" or name.startswith("alembic.")}:
        del sys.modules[name]


def check_migrations_needed():
    from services.apscheduler import scheduler

    with (engine := create_engine(cfg.green_db)).begin() as conn:
        diff = compare_metadata(
            MigrationContext.configure(conn, opts={"compare_type": compare_type}),
            [dbBase.metadata, scheduler.data_store.get_table_definitions()],
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


def auto_generate_migrations():
    try:
        command.revision(alembic_cfg, autogenerate=True, message="aha_auto_generated")
    except Exception as e:
        if "Target database is not up to date" in str(e):
            _logger.error(_("database.gen_version.not_up_to_date"))
        else:
            _logger.error(_("database.gen_version.error") % e)
        raise


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
