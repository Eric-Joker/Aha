from typing import overload

from sqlalchemy import BigInteger, Column, String, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from xxhash import xxh3_64_digest

from core.database import db_sessionmaker, dbBase
from models.core import Group, User
from utils.sqlalchemy import upsert

from .cache import async_cached, LRUCache
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


USER_CACHE = LRUCache(cfg.register("user_aha_id", 32768, _("identity.user.cache.cfg_comment"), module="cache"))
GROUP_CACHE = LRUCache(cfg.register("group_aha_id", 256, _("identity.group.cache.cfg_comment"), module="cache"))


def _generate_aha_id(platform, entity_id):
    """生成BLAKE3哈希的aha_id"""
    return int.from_bytes(xxh3_64_digest(platform + entity_id), signed=True)


# region 用户
@overload
async def user2aha_id(platform: str, user_id: str, *, session: AsyncSession = None) -> int: ...


@overload
async def user2aha_id(user_id: str, *, session: AsyncSession = None) -> int: ...


@overload
async def user2aha_id(*, session: AsyncSession = None) -> int: ...


@async_cached(USER_CACHE)
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

    if session is None:
        session = db_sessionmaker()
        should_close_session = True
    else:
        should_close_session = False

    try:
        result: int = await session.scalar(
            select(AhaUser.aha_id).where(AhaUser.platform == platform, AhaUser.user_id == user_id)
        )
        if result:
            return result

        # 不存在时生成
        aha_id = _generate_aha_id(platform, user_id)
        await session.execute(insert(AhaUser).values(platform=platform, user_id=user_id, aha_id=aha_id))

        if should_close_session:
            await session.commit()
        return aha_id
    finally:
        if should_close_session:
            await session.close()


async def aha_id2user(aha_id: int):
    """根据 Aha ID 反向查找用户"""
    async with db_sessionmaker() as session:
        return tuple(
            User(p, u)
            for p, u in (await session.scalars(select(AhaUser.platform, AhaUser.user_id).where(AhaUser.aha_id == aha_id))).all()
        )


async def map_user(source_platform: str, source_user_id: str, target_platform: str, target_user_id: str):
    """将一个平台的用户映射到另一个用户，建议不得映射自己"""
    async with db_sessionmaker() as session:
        target_aha_id = await user2aha_id(target_platform, target_user_id, session=session)

        if not target_aha_id:
            return False
        # 更新源用户的aha_id
        await session.execute(upsert(AhaUser, platform=source_platform, user_id=source_user_id, aha_id=target_aha_id))
        await session.commit()

    USER_CACHE[(source_platform, source_user_id)] = target_aha_id
    return True


# endregion
# region 群组
@overload
async def group2aha_id(platform: str, user_id: str) -> int: ...


@overload
async def group2aha_id(user_id: str) -> int: ...


@async_cached(GROUP_CACHE)
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

    async with db_sessionmaker() as session:
        result = await session.scalar(
            select(AhaGroup.aha_id).where(AhaGroup.platform == platform, AhaGroup.group_id == group_id)
        )
        if result:
            return result

        # 不存在时生成
        aha_id = _generate_aha_id(platform, group_id)
        await session.execute(insert(AhaGroup).values(platform=platform, group_id=group_id, aha_id=aha_id))
    return aha_id


async def aha_id2group(aha_id: int):
    """根据 Aha ID 反向查找群组"""
    async with db_sessionmaker() as session:
        return tuple(
            Group(p, g)
            for p, g in (
                await session.scalars(select(AhaGroup.platform, AhaGroup.group_id).where(AhaGroup.aha_id == aha_id))
            ).all()
        )


# endregion
