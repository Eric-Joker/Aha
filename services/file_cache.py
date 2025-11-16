from collections.abc import AsyncIterable, Iterable
from contextlib import suppress
from datetime import timedelta
from secrets import token_hex
from time import time
from typing import BinaryIO

from aiofiles import open
from anyio import Path
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import Column, Integer, select
from xxhash import xxh3_128, xxh3_128_hexdigest

from core.config import cfg
from core.database import db_session_factory, dbBase
from core.i18n import _
from models.metas import SingletonMeta
from models.sqlalchemy import Path as sqlPath
from services.apscheduler import scheduler
from utils.misc import MODULE_PATTERN, caller_module
from utils.sqlalchemy import upsert

CACHE_FILE_DIR = cfg.get_config("cache_file_path", Path("cache"), _("file_cache.path_cfg_comment"), "cache")
CACHE_FILE_CLEANUP = cfg.get_config("file_cleanup", "0 4 * * *", _("file_cache.cleanup.cfg_comment"), "cache")


class CacheFile(dbBase):
    __tablename__ = "cache_files"

    file_path = Column(sqlPath, primary_key=True)
    expires_at = Column(Integer, nullable=False)


class CacheFileManager(metaclass=SingletonMeta):
    __slots__ = ("cache_dir",)

    def __init__(self):
        self.cache_dir = CACHE_FILE_DIR

    async def start_service(self):
        await scheduler.add_schedule(self.cleanup, CronTrigger.from_crontab(CACHE_FILE_CLEANUP))
        self.cache_dir = await self.cache_dir.resolve()

    async def cache_file(
        self,
        ttl: timedelta | int,
        file_name: str | None = None,
        content: BinaryIO | bytes | str | AsyncIterable[bytes | str] | Iterable[bytes | str] | None = None,
        _level=2,
    ):
        """注册缓存文件

        当提供 `content`时，会将内容写入磁盘并返回路径，若未提供 `file_name` 则使用内容哈希作为文件名。

        未提供 `content` 时直接返回路径，若未提供 `file_name` 则使用随机16为 hex 字符作为文件名。

        Attributes:
            ttl: 至少有效期。配置中的 `file_cleanup` 触发时只会删除过期的文件。
        """

        expires_at = time() + (ttl.seconds if isinstance(ttl, timedelta) else ttl)

        if file_name:
            is_tmp = False
        else:
            file_name, is_tmp = await self._generate_filename(content)

        if module := caller_module(_level, MODULE_PATTERN):
            cache_dir = self.cache_dir / module
            await cache_dir.mkdir(parents=True, exist_ok=True)
        else:
            cache_dir = self.cache_dir

        file_path = cache_dir / file_name

        # 内容寻址
        if not is_tmp and await file_path.exists():
            await self._upsert_cache_record(file_path, expires_at)
            return file_path

        # 写入
        if content is not None:
            if (actual_hash := await self._write_content(content, file_path, is_tmp)) and is_tmp:
                if await (actual_path := cache_dir / actual_hash).exists():
                    await file_path.unlink(True)
                else:
                    await file_path.rename(actual_path)
                file_path = actual_path

        await self._upsert_cache_record(file_path, expires_at)
        return file_path

    @staticmethod
    async def _generate_filename(content):
        """生成基于内容或随机文件名"""
        if isinstance(content, (bytes, str)):
            return xxh3_128_hexdigest(content if isinstance(content, str) else content), False

        if hasattr(content, "seek") and hasattr(content, "read"):
            current_pos = content.tell()
            content.seek(0)
            hasher = xxh3_128()
            while chunk := content.read(8192):
                hasher.update(chunk)
            content.seek(current_pos)
            return hasher.hexdigest(), False

        return (token_hex(16), False) if content is None else (f"tmp_{token_hex(16)}", True)

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
                    async for chunk in content:
                        await f.write(data := chunk.encode("utf-8") if isinstance(chunk, str) else chunk)
                        hasher.update(data)

                else:  # 同步迭代器
                    for chunk in content:
                        await f.write(data := chunk.encode("utf-8") if isinstance(chunk, str) else chunk)
                        hasher.update(data)

                return hasher.hexdigest()

            if isinstance(content, (str, bytes)):
                await f.write(data := content.encode("utf-8") if isinstance(content, str) else content)

            elif hasattr(content, "read"):
                while chunk := content.read(8192):
                    await f.write(chunk)

            elif hasattr(content, "__aiter__"):
                async for chunk in content:
                    await f.write(chunk)

            else:  # 同步迭代器
                for chunk in content:
                    await f.write(data := chunk.encode("utf-8") if isinstance(chunk, str) else chunk)

    @staticmethod
    async def _upsert_cache_record(file_path, expires_at: int):
        """插入或更新缓存记录"""
        async with db_session_factory() as session:
            async with session.begin():
                await session.execute(select(CacheFile).where(CacheFile.file_path == file_path).with_for_update())
                await session.execute(upsert(CacheFile, file_path=file_path, expires_at=expires_at))
            await session.commit()

    @staticmethod
    async def cleanup():
        async with db_session_factory() as session:
            for cache_file in await session.scalars(
                select(CacheFile).where(CacheFile.expires_at <= time()).with_for_update(skip_locked=True)
            ):
                with suppress(OSError):
                    if await cache_file.file_path.exists():
                        await cache_file.file_path.unlink(True)
                    await session.delete(cache_file)

            await session.commit()


cfm = CacheFileManager()
