from typing import TYPE_CHECKING, overload

from aiologic import Lock
from sqlalchemy import BigInteger, Column, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from xxhash import xxh3_64_digest

from core.database import db_sessionmaker, dbBase
from models.core import Group, User
from utils.sqlalchemy import insert_ignore, upsert

from .cache import LRUCache
from .config import cfg
from .i18n import _


class AhaUser(dbBase):
    __tablename__ = "aha_users"

    platform = Column(String(16), primary_key=True)
    user_id = Column(String(255), primary_key=True)
    aha_id = Column(BigInteger, index=True)


class AhaGroup(dbBase):
    __tablename__ = "aha_groups"

    platform = Column(String(16), primary_key=True)
    group_id = Column(String(255), primary_key=True)
    aha_id = Column(BigInteger, index=True)


CACHER = LRUCache(cfg.register("aha_id", 32768, _("identity.cache.cfg_comment"), module="cache"))
CACHER_LOCK = Lock()


def _generate_aha_id(platform, entity_id):
    return int.from_bytes(xxh3_64_digest(platform + entity_id), signed=True)


# region 用户
if TYPE_CHECKING:

    @overload
    async def user2aha_id(platform: str, user_id: str, *, session: AsyncSession = None) -> int: ...

    @overload
    async def user2aha_id(user_id: str, *, session: AsyncSession = None) -> int: ...

    @overload
    async def user2aha_id(*, session: AsyncSession = None) -> int: ...


async def user2aha_id(arg1=None, arg2=None, session=None):
    """获取用户的 Aha ID，如果不存在则自动注册"""
    if arg2:
        platform, user_id = arg1, arg2
    else:
        from .dispatcher import current_event

        try:
            event = current_event.get()
        except AttributeError as e:
            raise RuntimeError(_("no_event_found_in_context")) from e
        try:
            platform, user_id = event.platform, arg1 or event.user_id
        except AttributeError as e:
            raise AttributeError(_("identity.uid404")) from e

    if not platform or not user_id:
        raise ValueError(f"Platform: {platform}, user id: {user_id}")

    async with CACHER_LOCK:
        if (result := CACHER.get((User, platform, user_id))) is not None:
            return result

    if session is None:
        session = db_sessionmaker()
        should_close_session = True
    else:
        should_close_session = False

    try:
        result = await session.scalar(
            insert_ignore(AhaUser, platform=platform, user_id=user_id, aha_id=_generate_aha_id(platform, user_id)).returning(
                AhaUser.aha_id
            )
        )

        if should_close_session:
            await session.commit()
        async with CACHER_LOCK:
            CACHER[(User, platform, user_id)] = result
        return result
    finally:
        if should_close_session:
            await session.close()


async def aha_id2user(aha_id: int) -> list[User]:
    """根据 Aha ID 反向查找用户"""
    async with CACHER_LOCK:
        if (result := CACHER.get((User, aha_id))) is not None:
            return result

    async with db_sessionmaker() as session:
        result = [
            User(p, u)
            for p, u in (await session.execute(select(AhaUser.platform, AhaUser.user_id).where(AhaUser.aha_id == aha_id))).all()
        ]

        async with CACHER_LOCK:
            CACHER[(User, aha_id)] = result
        return result


async def map_user(source_platform: str, source_user_id: str, target_platform: str, target_user_id: str):
    """将一个平台的用户映射到另一个用户，建议不得映射自己"""
    async with db_sessionmaker() as session:
        target_aha_id = await user2aha_id(target_platform, target_user_id, session=session)
        # 更新源用户的aha_id
        await session.execute(upsert(AhaUser, platform=source_platform, user_id=source_user_id, aha_id=target_aha_id))
        await session.commit()

    async with CACHER_LOCK:
        CACHER[(User, source_platform, source_user_id)] = target_aha_id
        if (cache := CACHER.get((User, target_aha_id), None)) is None:
            CACHER[(User, target_aha_id)] = cache = []
        cache.append(User(source_platform, source_user_id))
    return True


# endregion
# region 群组
if TYPE_CHECKING:

    @overload
    async def group2aha_id(platform: str, user_id: str) -> int: ...

    @overload
    async def group2aha_id(user_id: str) -> int: ...


async def group2aha_id(arg1=None, arg2=None):
    """获取群组的 Aha ID，如果不存在则自动注册"""
    if arg2:
        platform, group_id = arg1, arg2
    else:
        from .dispatcher import current_event

        try:
            event = current_event.get()
        except AttributeError as e:
            raise RuntimeError(_("no_event_found_in_context")) from e
        try:
            platform, group_id = event.platform, arg1 or event.group_id
        except AttributeError as e:
            raise AttributeError(_("identity.gid404")) from e

    if not platform or not group_id:
        raise ValueError(f"Platform: {platform}, group id: {group_id}")

    async with CACHER_LOCK:
        if (result := CACHER.get((Group, platform, group_id))) is not None:
            return result

    async with db_sessionmaker() as session:
        result = await session.scalar(
            insert_ignore(
                AhaGroup, platform=platform, group_id=group_id, aha_id=_generate_aha_id(platform, group_id)
            ).returning(AhaGroup.aha_id)
        )
        await session.commit()

    async with CACHER_LOCK:
        CACHER[(Group, platform, group_id)] = result
    return result


async def aha_id2group(aha_id: int) -> list[Group]:
    """根据 Aha ID 反向查找群组"""
    async with CACHER_LOCK:
        if (result := CACHER.get((Group, aha_id))) is not None:
            return result

    async with db_sessionmaker() as session:
        result = [
            Group(p, g)
            for p, g in (
                await session.execute(select(AhaGroup.platform, AhaGroup.group_id).where(AhaGroup.aha_id == aha_id))
            ).all()
        ]

        async with CACHER_LOCK:
            CACHER[(Group, aha_id)] = result
        return result


# endregion
