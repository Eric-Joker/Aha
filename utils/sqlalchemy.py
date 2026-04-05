from typing import TYPE_CHECKING

from sqlalchemy import Table, insert
from sqlalchemy.orm.decl_api import DeclarativeBase

if TYPE_CHECKING:
    from sqlalchemy.dialects.postgresql import Insert as PostgresInsert
    from sqlalchemy.dialects.sqlite import Insert as SqliteInsert


def upsert(table: type[DeclarativeBase] | Table, **kwargs) -> PostgresInsert | SqliteInsert:
    if not isinstance(table, Table):
        table = table.__table__

    primary_keys = [col.name for col in table.primary_key]
    return (stmt := insert(table).values(**kwargs)).on_conflict_do_update(index_elements=primary_keys, set_=stmt.excluded)


def insert_ignore(table: DeclarativeBase | Table, **kwargs) -> PostgresInsert | SqliteInsert:
    """插入数据，如果数据已存在（基于主键）则忽略"""
    if not isinstance(table, Table):
        table = table.__table__

    primary_keys = [col.name for col in table.primary_key]
    return (
        insert(table)
        .values(**kwargs)
        .on_conflict_do_update(index_elements=primary_keys, set_={primary_keys[0]: getattr(table.c, primary_keys[0])})
    )
