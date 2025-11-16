
from decimal import Decimal
from numbers import Number
from typing import overload

from sqlalchemy import insert, select, update

from core.identity import user2aha_id
from core.router import current_event
from core.database import db_session_factory

from sqlalchemy import BigInteger, Column, Numeric

from core.database import dbBase

__all__ = ("adjust_point", "inquiry_point", "Point")


class Point(dbBase):
    __tablename__ = "point"
    user_id = Column(BigInteger, primary_key=True)
    points = Column(Numeric, default=0)


@overload
async def adjust_point[T: Number](point: T, /) -> T:
    """调整点数，自动从上下文获取事件触发用户。"""


@overload
async def adjust_point[T: Number](platform: str, user: str, point: T, /) -> T:
    """调整点数

    Args:
        platform (str): 平台。
        user (str): 平台的用户 ID。
    """


@overload
async def adjust_point[T: Number](user: int, point: T, /) -> T:
    """调整点数

    Args:
        user (int): User's Aha ID.
    """


async def adjust_point(arg1, arg2=None, arg3=None, /):
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

    async with db_session_factory() as session:
        result = await session.execute(update(Point).where(Point.user_id == user).values(points=Point.points + points))
        if result.rowcount == 0:
            await session.execute(insert(Point).values(user_id=user, points=points))
        await session.commit()
    return points


@overload
async def inquiry_point() -> Decimal:
    """查询点数，自动从上下文获取事件触发用户。"""


@overload
async def inquiry_point(platform: str, user: str, /) -> Decimal:
    """查询点数

    Args:
        platform (str): 平台。
        user (str): 平台的用户 ID。
    """


@overload
async def inquiry_point(user: int, /) -> Decimal:
    """查询点数

    Args:
        user (int): User's Aha ID.
    """


async def inquiry_point(arg1=None, arg2=None, /):
    async with db_session_factory() as session:
        if arg1:
            user = (await user2aha_id(arg1, arg2, session=session)) if arg2 else arg1
        else:
            user = await current_event.get().user_aha_id()
        return (await session.scalar(select(Point.points).filter(Point.user_id == user))) or Decimal(0)
