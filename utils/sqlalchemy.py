from sqlalchemy import Table
from sqlalchemy.orm.decl_api import DeclarativeBase

from core.database import db_engine
from core.i18n import _

match dialect_name := db_engine.dialect.name:
    case "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    case "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    case "mysql":
        from sqlalchemy.dialects.mysql import insert


def upsert(table: type[DeclarativeBase] | Table, **kwargs):
    if not isinstance(table, Table):
        table = table.__table__
    if not (primary_key_names := [col.name for col in table.primary_key]):
        raise ValueError(_("sqlalchemy_upsert.404"))

    # 非主键字段
    update_dict = {
        col.name: kwargs[col.name]
        for col in table.columns
        if col.name not in primary_key_names and col.name in kwargs
    }

    match dialect_name:
        case "postgresql" | "sqlite":
            return insert(table).values(**kwargs).on_conflict_do_update(index_elements=primary_key_names, set_=update_dict)

        # 没测试过
        case "mysql":
            stmt = insert(table).values(**kwargs)
            return stmt.on_duplicate_key_update(**{k: stmt.inserted[k] for k in update_dict})

        case _:
            raise NotImplementedError({dialect_name})


def insert_ignore(table: DeclarativeBase | Table, **kwargs):
    """插入数据，如果数据已存在（基于主键）则忽略"""
    if not isinstance(table, Table):
        table = table.__table__
    if not (primary_key_names := [col.name for col in table.primary_key]):
        raise ValueError(_("sqlalchemy_insert_ignore.404"))

    match dialect_name:
        case "postgresql" | "sqlite":
            return insert(table).values(**kwargs).on_conflict_do_nothing(index_elements=primary_key_names)

        # 没测试过
        case "mysql":
            return insert(table).values(**kwargs).prefix_with("IGNORE")

        case _:
            raise NotImplementedError({dialect_name})
