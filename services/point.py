from decimal import Decimal
from numbers import Number
from typing import TYPE_CHECKING, overload

from sqlalchemy import BigInteger, Column, Numeric, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import db_sessionmaker, dbBase
from core.identity import user2aha_id
from core.dispatcher import current_event

__all__ = ("adjust_point", "get_point", "Point")


class Point(dbBase):
    __tablename__ = "point"
    user_id = Column(BigInteger, primary_key=True)
    points = Column(Numeric, default=0)


if TYPE_CHECKING:

    @overload
    async def adjust_point(delta: Number, /, *, session: AsyncSession = None) -> Decimal:
        """调整点数，自动从上下文获取事件触发用户"""

    @overload
    async def adjust_point(platform: str, user: str, delta: Number, /, session: AsyncSession = None) -> Decimal:
        """调整点数

        Args:
            platform (str): 平台。
            user (str): 平台的用户 ID。
        """

    @overload
    async def adjust_point(user: int, delta: Number, /, *, session: AsyncSession = None) -> Decimal:
        """调整点数

        Args:
            user (int): User's Aha ID.
        """


async def adjust_point(arg1, arg2=None, arg3=None, /, session=None):
    if arg2 is None:
        user = await current_event.get().user_aha_id()
        delta = arg1
    elif arg3 is None:
        user = arg1
        delta = arg2
    else:
        user = await user2aha_id(arg1, arg2)
        delta = arg3

    if session is None:
        session = db_sessionmaker()
        should_close_session = True
    else:
        should_close_session = False

    try:
        result = await session.scalar(
            insert(Point)
            .values(user_id=user, points=delta)
            .on_conflict_do_update(index_elements=(Point.user_id,), set_={Point.points: Point.points + delta})
            .returning(Point.points)
        )
        if should_close_session:
            await session.commit()
        return result
    finally:
        if should_close_session:
            await session.close()


if TYPE_CHECKING:

    @overload
    async def get_point(*, session: AsyncSession = None) -> Decimal:
        """查询点数，自动从上下文获取事件触发用户"""

    @overload
    async def get_point(platform: str, user: str, /, session: AsyncSession = None) -> Decimal:
        """查询点数

        Args:
            platform (str): 平台。
            user (str): 平台的用户 ID。
        """

    @overload
    async def get_point(user: int, /, *, session: AsyncSession = None) -> Decimal:
        """查询点数

        Args:
            user (int): User's Aha ID.
        """


async def get_point(arg1=None, arg2=None, /, session=None):
    if session is None:
        session = db_sessionmaker()
        should_close_session = True
    else:
        should_close_session = False

    try:
        if arg1 is None:
            user = await current_event.get().user_aha_id()
        elif arg2 is None:
            user = arg1
        else:
            user = await user2aha_id(arg1, arg2, session=session)
        return (await session.scalar(select(Point.points).filter(Point.user_id == user))) or Decimal(0)
    finally:
        if should_close_session:
            await session.close()
