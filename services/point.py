from decimal import Decimal
from numbers import Number
from typing import overload

from sqlalchemy import BigInteger, Column, Numeric, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import db_sessionmaker, dbBase
from core.identity import user2aha_id
from core.dispatcher import current_event

__all__ = ("adjust_point", "inquiry_point", "Point")


class Point(dbBase):
    __tablename__ = "point"
    user_id = Column(BigInteger, primary_key=True)
    points = Column(Numeric, default=0)


@overload
async def adjust_point(point: Number, /, *, session: AsyncSession = None) -> Decimal:
    """调整点数，自动从上下文获取事件触发用户"""


@overload
async def adjust_point(platform: str, user: str, point: Number, /, session: AsyncSession = None) -> Decimal:
    """调整点数

    Args:
        platform (str): 平台。
        user (str): 平台的用户 ID。
    """


@overload
async def adjust_point(user: int, point: Number, /, *, session: AsyncSession = None) -> Decimal:
    """调整点数

    Args:
        user (int): User's Aha ID.
    """


async def adjust_point(arg1, arg2=None, arg3=None, /, session=None):
    if arg2:
        if arg3:
            user = await user2aha_id(arg1, arg2)
            points = arg3
        else:
            user = arg1
            points = arg2
    else:
        user = await current_event.get().user_aha_id()
        points = arg1

    if session is None:
        session = db_sessionmaker()
        should_close_session = True
    else:
        should_close_session = False

    try:
        result = await session.execute(update(Point).where(Point.user_id == user).values(points=Point.points + points).returning(Point.points))
        if result.rowcount == 0:
            result = await session.execute(insert(Point).values(user_id=user, points=points).returning(Point.points))
        await session.commit()
        return result.scalar_one()
    finally:
        if should_close_session:
            await session.close()


@overload
async def inquiry_point(*, session: AsyncSession = None) -> Decimal:
    """查询点数，自动从上下文获取事件触发用户"""


@overload
async def inquiry_point(platform: str, user: str, /, session: AsyncSession = None) -> Decimal:
    """查询点数

    Args:
        platform (str): 平台。
        user (str): 平台的用户 ID。
    """


@overload
async def inquiry_point(user: int, /, *, session: AsyncSession = None) -> Decimal:
    """查询点数

    Args:
        user (int): User's Aha ID.
    """


async def inquiry_point(arg1=None, arg2=None, /, session=None):
    if session is None:
        session = db_sessionmaker()
        should_close_session = True
    else:
        should_close_session = False

    try:
        if arg1:
            user = (await user2aha_id(arg1, arg2, session=session)) if arg2 else arg1
        else:
            user = await current_event.get().user_aha_id()
        return (await session.scalar(select(Point.points).filter(Point.user_id == user))) or Decimal(0)
    finally:
        if should_close_session:
            await session.close()
