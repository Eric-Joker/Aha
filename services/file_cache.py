import os
from asyncio import Lock
from collections import defaultdict
from collections.abc import AsyncIterable, Iterable
from contextlib import asynccontextmanager, suppress
from datetime import timedelta
from secrets import token_hex
from time import time
from typing import BinaryIO

from aiofiles import open
from anyio import Path
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import Column, Integer, select, update
from xxhash import xxh3_128, xxh3_128_hexdigest

from core.config import cfg
from core.database import db_sessionmaker, dbBase
from core.i18n import _
from models.sqlalchemy import Path as sqlPath
from services.apscheduler import sched
from utils.misc import AHA_MODULE_PATTERN, caller_aha_module
from utils.sqlalchemy import upsert

__all__ = "cache_file_sessionmaker"

CFGS = cfg.register(
    "file_cache",
    {"dir": Path(os.path.abspath("cache")), "cleanup_cron": "0 4 * * *"},
    _("file_cache.cfg_comment"),
    module="cache",
)
CACHE_DIR = CFGS["dir"]


class CacheFile(dbBase):
    __tablename__ = "cache_files"

    file_path = Column(sqlPath, primary_key=True)
    expires_at = Column(Integer, nullable=False)


class CacheFileSession:
    __slots__ = ("db_session", "transaction", "dir", "filename", "path", "locks")

    LOCKED: defaultdict[Path, Lock] = defaultdict(Lock)

    def __init__(self, dir: Path, name: str):
        self.dir = dir
        self.filename = name
        if name:
            self.path = self.dir / name
        self.db_session = db_sessionmaker()
        self.transaction = None
        self.locks: dict[Path, Lock] = {}

    async def __aenter__(self):
        await self.db_session.__aenter__()
        self.transaction = self.db_session.begin()
        await self.transaction.__aenter__()
        if self.filename:
            await self._acquire_lock(self.path)
        return self

    async def _acquire_lock(self, path):
        self.locks[path] = lock = self.LOCKED[path]
        await lock.acquire()
        await self.db_session.execute(select(CacheFile).where(CacheFile.file_path == path).with_for_update())

    async def get_and_refresh(self, ttl: timedelta | int):
        if self.filename and await self.path.exists():
            await self.db_session.execute(
                update(CacheFile)
                .where(CacheFile.file_path == self.path)
                .values(expires_at=time() + (ttl.seconds if isinstance(ttl, timedelta) else ttl))
            )
            return self.path

    @staticmethod
    async def _write_content(content, file_path, is_tmp):
        """将内容写入文件并返回哈希值（如果需要）"""
        if is_tmp:
            hasher = xxh3_128()

        async with open(file_path, "wb") as f:
            if is_tmp:
                if isinstance(content, (str, bytes)):
                    await f.write(data := content.encode("utf-8") if isinstance(content, str) else content)
                    hasher.update(data)

                elif hasattr(content, "read"):
                    while chunk := content.read(8192):
                        await f.write(chunk)
                        hasher.update(chunk)

                elif hasattr(content, "__aiter__"):
                    chunk = await anext(content)
                    if isinstance(chunk, str):
                        await f.write(chunk := chunk.encode("utf-8"))
                        hasher.update(chunk)
                        async for chunk in content:
                            await f.write(chunk := chunk.encode("utf-8"))
                            hasher.update(chunk)
                    else:
                        await f.write(chunk)
                        hasher.update(chunk)
                        async for chunk in content:
                            await f.write(chunk)
                            hasher.update(chunk)

                else:  # 同步迭代器
                    chunk = next(content)
                    if isinstance(chunk, str):
                        await f.write(chunk := chunk.encode("utf-8"))
                        hasher.update(chunk)
                        for chunk in content:
                            await f.write(chunk := chunk.encode("utf-8"))
                            hasher.update(chunk)
                    else:
                        await f.write(chunk)
                        hasher.update(chunk)
                        for chunk in content:
                            await f.write(chunk)
                            hasher.update(chunk)

                return hasher.hexdigest()

            if isinstance(content, (str, bytes)):
                await f.write(data := content.encode("utf-8") if isinstance(content, str) else content)

            elif hasattr(content, "read"):
                while chunk := content.read(8192):
                    await f.write(chunk)

            elif hasattr(content, "__aiter__"):
                chunk = await anext(content)
                if isinstance(chunk, str):
                    await f.write(chunk := chunk.encode("utf-8"))
                    async for chunk in content:
                        await f.write(chunk := chunk.encode("utf-8"))
                else:
                    await f.write(chunk)
                    async for chunk in content:
                        await f.write(chunk)

            else:  # 同步迭代器
                chunk = next(content)
                if isinstance(chunk, str):
                    await f.write(chunk := chunk.encode("utf-8"))
                    for chunk in content:
                        await f.write(chunk := chunk.encode("utf-8"))
                else:
                    await f.write(chunk)
                    for chunk in content:
                        await f.write(chunk)

    async def register(
        self, ttl: timedelta | int, content: BinaryIO | bytes | str | AsyncIterable[bytes | str] | Iterable[bytes | str] = None
    ):
        """注册缓存文件

        Attributes:
            ttl: 至少有效期。配置中的 `file_cache.cleanup_cron` 触发时只会删除过期的文件。
            content: 文件内容。提供时会写入磁盘并返回路径，不提供时直接返回路径。
        """
        ttl = ttl.seconds if isinstance(ttl, timedelta) else ttl

        # 无需写入
        if content is None:
            if not self.filename:
                self.filename = token_hex(16)
                self.path = self.dir / self.filename
                await self._acquire_lock(self.path)
            await self.db_session.execute(upsert(CacheFile, file_path=self.path, expires_at=time() + ttl))
            return self.path

        # 生成文件路径
        if self.filename:
            is_tmp = False
        else:
            if isinstance(content, (bytes, str)):
                self.filename, is_tmp = xxh3_128_hexdigest(content), False
            else:
                self.filename, is_tmp = f"tmp_{token_hex(16)}", True
            self.path = self.dir / self.filename
            await self._acquire_lock(self.path)

        # 写入
        if (actual_hash := await self._write_content(content, self.path, is_tmp)) and is_tmp:
            self._acquire_lock(actual_path := self.dir / actual_hash)
            # 长效化临时
            if await actual_path.exists():
                await self.path.unlink(True)
            else:
                await self.path.rename(actual_path)
            self.path = actual_path

        await self.db_session.execute(upsert(CacheFile, file_path=self.path, expires_at=time() + ttl))
        return self.path

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.transaction.__aexit__(exc_type, exc_val, exc_tb)
        for k, v in self.locks.items():
            v.release()
            del self.LOCKED[k]
        await self.db_session.__aexit__(exc_type, exc_val, exc_tb)


async def start_file_cache_service():
    global CACHE_DIR
    await sched.add_schedule(cleanup, CronTrigger.from_crontab(CFGS["cleanup_cron"]))
    CACHE_DIR = await CACHE_DIR.resolve()


@asynccontextmanager
async def cache_file_sessionmaker(file_name=None, _level=2):
    """获取缓存文件工作会话

    Args:
        file_name: 未提供时会采用内容哈希或随机16位 hex。
    """
    if module := caller_aha_module(_level, AHA_MODULE_PATTERN):
        cache_dir = CACHE_DIR / module
    else:
        cache_dir = CACHE_DIR
    await CACHE_DIR.mkdir(parents=True, exist_ok=True)

    async with CacheFileSession(cache_dir, file_name) as session:
        yield session


async def cleanup():
    async with db_sessionmaker() as session:
        async with session.begin():
            for cache_file in await session.scalars(
                select(CacheFile).where(CacheFile.expires_at <= time()).with_for_update(skip_locked=True)
            ):
                with suppress(OSError):
                    if await cache_file.file_path.exists():
                        await cache_file.file_path.unlink(True)
                    await session.delete(cache_file)
            await session.commit()
