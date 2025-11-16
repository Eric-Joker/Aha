# 本文件修改自 https://github.com/liyihao1110/ncatbot
import logging
import os
from asyncio import create_task, to_thread
from collections.abc import AsyncGenerator, AsyncIterable, Iterable
from contextlib import asynccontextmanager
from logging import getLogger
from re import escape
from types import NoneType
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, Literal, SupportsIndex, dataclass_transform, overload
from urllib.parse import urlparse

from aiofiles import open
from anyio import Path
from httpx import HTTPStatusError
from lxml.etree import XML, _Element
from orjson import loads
from pydantic import BeforeValidator, Field, GetCoreSchemaHandler, field_serializer, field_validator, model_validator
from pydantic._internal._model_construction import ModelMetaclass
from pydantic_core import core_schema
from tenacity import before_sleep_log, retry, retry_if_exception_type, stop_after_attempt, wait_fixed
from xxhash import xxh3_64_intdigest

from core.i18n import _
from utils.aio import AsyncTee
from utils.network import get_httpx_client

from .api.utils import AudioFormat
from .base import BaseModel
from .exc import DownloadFileMsgError, UnknownMessageTypeError

if TYPE_CHECKING:
    from PIL.Image import Image as PilImage
    from pydantic._internal._model_construction import NoInitField
    from pydantic.fields import Field as PydanticModelField
    from pydantic.fields import PrivateAttr as PydanticModelPrivateAttr
else:
    PydanticModelField = object()
    PydanticModelPrivateAttr = object()
    NoInitField = object()

logger = getLogger("AHA")


@dataclass_transform(kw_only_default=True, field_specifiers=(PydanticModelField, PydanticModelPrivateAttr, NoInitField))
class MsgSegMeta(ModelMetaclass):
    def __str__(cls: type):
        if issubclass(cls, Text):
            return r"(?P<text>[^\[]+)"
        if issubclass(cls, (Forward, Node)):
            raise NotImplementedError(_("models.msg.cls2pattern.forward501"))
        return rf"\[Aha:{cls.__name__.lower()}{"".join(rf"(?:,{n}=(?P<{n}>[\s\S]*?))?" for n, i in cls.model_fields.items() if not i.exclude)}\]"

    def prefixed_re_group(cls: type, prefix):
        if issubclass(cls, Text):
            return rf"(?P<{prefix}text>[^\[]+)"
        if issubclass(cls, (Forward, Node)):
            raise NotImplementedError(_("models.msg.cls2pattern.forward501"))
        return rf"\[Aha:{cls.__name__.lower()}{"".join(rf"(?:,{n}=(?P<{prefix}{n}>[\s\S]*?))?" for n, i in cls.model_fields.items() if not i.exclude)}\]"


class MsgSeg(BaseModel, metaclass=MsgSegMeta):
    """消息段基类"""

    async def serialize(self):
        """转换为字典格式，排除空值和None字段"""
        data = {}
        for k, v in self.model_dump(by_alias=True, exclude_none=True).items():
            if v.__class__ is list and (chain := getattr(self, k, None)) and isinstance(chain, MessageChain):
                data[k] = [await seg.serialize() for seg in chain]
            elif v:
                data[k] = v

        return {"type": self.__class__.__name__.lower(), "data": data}

    def __str__(self):
        from utils.aha import escape_aha

        strings = [f"[Aha:{self.__class__.__name__.lower()}"]
        for k, v in self.model_dump(by_alias=True, exclude_none=True).items():
            if v.__class__ is list and (chain := getattr(self, k, None)) and isinstance(chain, MessageChain):
                strings.append(f"{k}={"".join(str(seg) for seg in chain)}")
            else:
                strings.append(f"{k}={escape_aha(str(v))}")
        return f"{",".join(strings)}]"

    @property
    def pattern(self):
        return escape(str(self))

    def __repr__(self):
        return self.__str__()


class MessageChain[T: MsgSeg](list[T]):
    """消息数组，包含多个消息段。

    Note:
        `Node` 不得与其他类型的实例在一个消息链中混用。
    """

    _event_type_cache: ClassVar[dict[str, type[MsgSeg]]] = {}

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler: GetCoreSchemaHandler):
        return core_schema.no_info_after_validator_function(
            cls, handler(list[args[0] if (args := getattr(source_type, "__args__", None)) else Any])
        )

    @overload
    def __init__(self) -> None: ...

    @overload
    def __init__(self, *elements: str | T) -> None: ...

    @overload
    def __init__(self, iterable: Iterable[str | T], /) -> None: ...

    def __init__(self, *args, bot_id=None):
        self.bot_id = bot_id

        if not args:
            super().__init__()
        elif len(args) == 1:
            if isinstance(arg := args[0], str):
                super().__init__((Text(text=arg),))
            elif isinstance(arg, MsgSeg):
                super().__init__(args)
            else:
                super().__init__(a if isinstance(a, MsgSeg) else Text(text=str(a)) for a in arg)
        else:
            super().__init__(arg if isinstance(arg, MsgSeg) else Text(text=str(arg)) for arg in args)

    def __str__(self):
        return "".join(str(item) for item in self)

    def __repr__(self):
        return self.__str__()

    @classmethod
    def from_pydantic(cls, value):
        return value if isinstance(value, cls) else cls(value)

    @overload
    def __setitem__(self, key: SupportsIndex, value: T) -> None: ...
    @overload
    def __setitem__(self, key: slice, value: Iterable[T]) -> None: ...

    def __setitem__(self, key, value):
        if isinstance(key, slice):
            super().__setitem__(key, [v if isinstance(v, MsgSeg) else Text(text=str(v)) for v in value])
        else:
            super().__setitem__(key, value if isinstance(value, MsgSeg) else Text(text=str(value)))

    def extend(self, iterable: Iterable[T]):
        super().extend(i if isinstance(i, MsgSeg) else Text(text=str(i)) for i in iterable)

    def append(self, item: T):
        super().append(item if isinstance(item, MsgSeg) else Text(text=str(item)))

    def insert(self, index: SupportsIndex, item: T):
        super().insert(index, item if isinstance(item, MsgSeg) else Text(text=str(item)))

    def __add__(self, other: MessageChain):
        return MessageChain(super().__add__(other), bot_id=self.bot_id)

    def __iadd__(self, iterable: Iterable[T]):
        self.extend(iterable)
        return self

    def __radd__(self, other: MessageChain):
        return self.__add__(other)

    def __mul__(self, value: SupportsIndex):
        return MessageChain(super().__mul__(value), bot_id=self.bot_id)

    def __rmul__(self, value: SupportsIndex):
        return MessageChain(super().__rmul__(value), bot_id=self.bot_id)

    def copy(self):
        return MessageChain(super().copy(), bot_id=self.bot_id)

    async def serialize(self) -> list[dict]:
        return [await item.serialize() for item in self]

    async def plain_forward_msg(self: MessageChain[Forward], bot_id: int = None):
        """把转发id格式的消息展平为解析完毕的 Forward"""
        from core.api import API

        return await API.get_forward_msg(self[0].id, bot=bot_id)

    def filter(self, cls: type[MsgSeg] | None = None):
        """过滤特定类型的消息段"""
        if cls is None:
            return self.copy()
        return MessageChain([item for item in self if isinstance(item, cls)], bot_id=self.bot_id)

    def is_user_at(self, user_id: str | int, include_all=False):
        """检查是否@了指定用户"""
        user_id = str(user_id)
        return any(
            (isinstance(item, At) and item.user_id == user_id) or (include_all and item.user_id == "all") for item in self
        )

    @classmethod
    def get_seg_class(cls, name: str) -> type[MsgSeg]:
        """根据名称获取消息段类"""
        try:
            if not cls._event_type_cache:
                # 动态查找所有消息段子类
                subclasses: set[type[MsgSeg]] = set()
                to_check = [MsgSeg]

                while to_check:
                    current = to_check.pop()
                    for subclass in current.__subclasses__():
                        if subclass not in subclasses:
                            subclasses.add(subclass)
                            to_check.append(subclass)

                # 构建消息类型缓存
                for msg_cls in subclasses:
                    cls._event_type_cache[msg_cls.__name__.lower()] = msg_cls

            return cls._event_type_cache[name]
        except KeyError as e:
            raise UnknownMessageTypeError(e) from e


MsgSeq = MsgChain = MsgList = MessageChain


class Downloadable(MsgSeg):
    """可下载消息段。

    Attributes:
        file: 可为本地文件路径、HTTP(s) URL，若为 bytes 则是文件内容，但后者不能用于调用 API。
        name: 文件名。

    note: 有些协议可能限制发送的文件大小，见协议文档。
    """

    file: str | Path | bytes | AsyncIterable | None = None
    name: str = None
    file_id: str | int | tuple | bytes | frozenset = None
    thumb: str | None = None

    file_type: str | None = Field(None, init=False)
    file_size: int | None = Field(None, init=False)

    bot_id: int | None = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="after")
    def valid_name(self):
        if not self.name:
            self.get_file_name()
        if self.file_id is None:
            self.file_id = self.name
        return self

    def get_file_name(self):
        if isinstance(self.file, str):
            if self.file.startswith(("http://", "https://", "ftp://", "s3://")):
                if name := (parsed := urlparse(self.file)).path or parsed.netloc.partition(":")[0]:
                    self.name = os.path.basename(name).partition("?")[0].partition("#")[0]
            else:
                self.name = os.path.basename(self.file)
        elif isinstance(self.file, Path):
            self.name = self.file.name
        return self.name

    @staticmethod
    def _detect_extension(header) -> str | None:
        """根据文件头部字节识别扩展名，失败返回 None"""
        if (hlen := len(header)) >= 2:
            match header[:2]:
                case b"\xff\xd8":  # JPEG (also covers MPO)
                    return "jpg"
                case b"BM":  # BMP / DIB
                    return "bmp"
                case b"PF" | b"Pf":
                    return "pfm"
                case b"\x01\xda":
                    return "sgi"
            if header[0] == 80 and header[1] in b"123456":
                return "ppm"
        if hlen >= 6 and header[:6] in (b"GIF87a", b"GIF89a"):  # GIF
            return "gif"
        if hlen >= 8 and header[:8] == b"\x89PNG\r\n\x1a\n":  # PNG
            return "png"
        if hlen >= 12:
            if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
                return "webp"
            if header[4:8] == b"ftyp" and header[8:12] in (b"avif", b"avis"):
                return "avif"
            if header[4:8] in (b"jP  ", b"jp2 ", b"jpx "):  # JPEG 2000
                return "jp2"
        if hlen >= 4:
            match header[:4]:
                case b"II\x2a\x00" | b"MM\x00\x2a":
                    return "tiff"
                case b"%PDF":
                    return "pdf"
                case b"\x00\x00\x01\x00" | b"\x00\x00\x02\x00":
                    return "ico"
                case b"%!PS":
                    return "eps"
                case b"DDS ":
                    return "dds"
                case b"qoif":
                    return "qoi"
                case b"BLP1" | b"BLP2":
                    return "blp"
        return "pcx" if hlen >= 1 and header[0] == 0x0A else None

    @overload
    async def download(self, dir_: str | Path = None, name: str | None = None, *, bot_id: int = None) -> Path: ...

    async def download(self, dir_=None, name=None, fix_ext=True, record_format=AudioFormat.MP3, bot_id=None):
        """下载文件

        指定 `dir_` 时，将文件保存到指定目录，覆盖同名文件，并返回保存路径。

        未指定 `dir_` 时，若本地路径存在文件，则直接返回路径；否则返回缓存文件路径。

        Returns:
            文件路径。若不存在文件源则返回 None。

        Raises:
            models.exc.APIException: 下载时出现 HTTP 错误。
        """
        if not self.file:
            return None
        if not name:
            name = self.name
        if dir_:
            dir_ = Path(dir_)

        from core.config import cfg
        from services.file_cache import cache_file_sessionmaker

        async with cache_file_sessionmaker(name) as session:
            # 在标准文件缓存的远程文件
            if not dir_ and (path := await session.get_and_refresh(cfg.file_msg_ttl)):
                return path

            # 源文件就是本地文件
            if await (path := Path(self.file)).exists():
                return await path.copy(dir_ / name) if dir_ else path

            # 更新文件源
            from core.api import API

            if isinstance(self, File) and self.group_id:
                self.file = await API.get_group_file_url(self.group_id, self.file_id, bot=bot_id or self.bot_id)
            else:
                self.file = await API.get_file_src(self, record_format, bot=bot_id)

                # 缓存 bytes
                if type(self.file) is bytes:
                    self.file = await session.register(cfg.file_msg_ttl, self.file)
                    return await self.file.copy(dir_ / name) if dir_ else self.file

            # 下载远程文件
            try:
                async with self._http_request() as response:
                    response.raise_for_status()

                    chunks, byte_iter = [], response.aiter_bytes()
                    if fix_ext and isinstance(self, Image):
                        total = 0
                        while total < 18:
                            try:
                                chunks.append(chunk := await byte_iter.__anext__())
                            except StopAsyncIteration:
                                break
                            total += len(chunk)

                        if chunks:
                            if len(chunks[0]) >= 18:
                                header_bytes = chunks[0][:18]
                            else:
                                buf = bytearray()
                                for c in chunks:
                                    buf.extend(c)
                                    if len(buf) >= 18:
                                        break
                                header_bytes = bytes(buf[:18])

                        # 修正
                        if ext := self._detect_extension(header_bytes):
                            name = f"{os.path.splitext(name)[0]}.{ext}"

                    async def content_iter():
                        for c in chunks:
                            yield c
                        async for c in byte_iter:
                            yield c
                    if dir_:
                        async with open(path := dir_ / name, "wb") as f:
                            if fix_ext:
                                for c in chunks:
                                    await f.write(c)
                            async for c in byte_iter:
                                await f.write(c)
                        return path
                    else:
                        return await session.register(cfg.file_msg_ttl, content_iter() if fix_ext else response.aiter_bytes())
            except HTTPStatusError as e:
                raise DownloadFileMsgError(_("models.msg.downloadable.http_error") % e) from None

    @overload
    async def stream(self, size=8192, *, bot_id: int = None) -> AsyncGenerator[bytes, Any, None]: ...

    async def stream(self, size=8192, record_format=AudioFormat.MP3, bot_id=None):
        """获取文件流，若文件源不存在为空生成器。

        Raises:
            models.exc.APIException: 下载时出现 HTTP 错误。
        """
        if not self.file:
            return

        from core.config import cfg
        from services.file_cache import cache_file_sessionmaker

        async with cache_file_sessionmaker(self.name) as session:
            # 在标准文件缓存的远程文件
            if path := await session.get_and_refresh(cfg.file_msg_ttl):
                async with open(path, "rb") as f:
                    while chunk := await f.read(size):
                        yield chunk
                return

            # 源文件就是本地文件
            if await (path := Path(self.file)).exists():
                async with open(path, "rb") as f:
                    while chunk := await f.read(8192):
                        yield chunk
                return

            # 更新文件源
            from core.api import API

            if isinstance(self, File) and self.group_id:
                self.file = await API.get_group_file_url(self.group_id, self.file_id, bot=bot_id or self.bot_id)
            else:
                self.file = await API.get_file_src(self, record_format, bot=bot_id)

                # 缓存 bytes
                if type(self.file) is bytes:
                    data = self.file
                    self.file = await session.register(cfg.file_msg_ttl, self.file)
                    for i in range(0, len(data), size):
                        yield data[i : i + size]
                    return

            # 下载远程文件
            try:
                async with self._http_request() as response:
                    response.raise_for_status()

                    gen1, gen2 = AsyncTee.gen(response.aiter_bytes(size))
                    task = create_task(session.register(cfg.file_msg_ttl, gen2))
                    async for chunk in gen1:
                        yield chunk
                    await task
            except HTTPStatusError as e:
                raise DownloadFileMsgError(_("models.msg.downloadable.http_error") % e) from None

    @asynccontextmanager
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type(HTTPStatusError),
        before_sleep=before_sleep_log(getLogger("Aha (download msg file)"), logging.WARNING),
        reraise=True,
    )
    async def _http_request(self):
        async with get_httpx_client().stream("GET", self.file) as response:
            response.raise_for_status()
            yield response


class Text(MsgSeg):
    """纯文本消息段"""

    text: str

    def __str__(self):
        from utils.aha import escape_aha

        return escape_aha(self.text)

    def __repr__(self):
        return repr(self.text)

    def __eq__(self, other):
        return self.text == other if isinstance(other, str) else NotImplemented

    def __hash__(self):
        return xxh3_64_intdigest(self.text)


class Image(Downloadable):
    summary: str | None = None
    sub_type: Any | None = None

    @overload
    async def download(self, dir_: str | Path = None, name: str = None, *, fix_ext=True, bot_id: int = None) -> Path | None: ...

    async def download(self, dir_=None, name=None, fix_ext=True, bot_id=None):
        return await super().download(dir_, name, fix_ext=fix_ext, bot_id=bot_id)

    @classmethod
    async def from_pil(
        cls,
        image: PilImage,
        format_: Literal[
            "AVIF",
            "BLP",
            "BMP",
            "DDS",
            "DIB",
            "EPS",
            "GIF",
            "ICO",
            "IM",
            "JPEG",
            "JPEG 2000",
            "MPO",
            "MSP",
            "PCX",
            "PFM",
            "PNG",
            "PPM",
            "QOI",
            "SGI",
            "SPIDER",
            "TGA",
            "TIFF",
            "WebP",
            "XBM",
            "PALM",
            "PDF",
        ] = "JPEG",
        ttl=86400,
        name: str = None,
        summary: str | None = None,
    ):
        from services.file_cache import cache_file_sessionmaker

        async with cache_file_sessionmaker(name, 3) as session:
            await to_thread(image.save, path := await session.register(ttl), format=format_)
        return cls(file=path, name=name or path.name, summary=summary)


class Sticker(Downloadable):
    summary: str | None = None
    sub_type: Any | None = None


class File(Downloadable):
    group_id: str | None = Field(default=None, exclude=True)

    async def serialize(self):
        (dict_data := await super().serialize())["data"]["name"] = self.get_file_name()
        return dict_data


class Record(Downloadable):
    @overload
    async def download(
        self, dir_: str | Path = None, name: str = None, *, record_format: AudioFormat = AudioFormat.MP3, bot_id: int = None
    ) -> Path | None: ...

    async def download(self, dir_=None, name=None, record_format=AudioFormat.MP3, bot_id=None):
        return await super().download(
            dir_, f"{os.path.splitext(name or self.name)[0]}.{record_format.value}", record_format=record_format, bot_id=bot_id
        )

    @overload
    async def stream(
        self, size=8192, record_format: AudioFormat = AudioFormat.MP3, bot_id: int = None
    ) -> AsyncGenerator[bytes, Any, None]: ...

    async def stream(self, size=8192, record_format=AudioFormat.MP3, bot_id=None):
        return await super().stream(size, record_format, bot_id)


class Video(Downloadable):
    pass


class At(MsgSeg):
    """@消息段"""

    user_id: Annotated[str, BeforeValidator(str)] | None = None
    name: str | None = Field(None, init=False)

    @classmethod
    def all(cls) -> At:
        return At(user_id="all")

    def is_all(self) -> bool:
        return self.user_id == "all"


class Share(MsgSeg):
    """分享消息段
    
    Attributes:
        image: 封面图源，可以为路径或链接。
    """

    url: str
    title: str | None = None
    content: str | None = None
    image: str | Path | AsyncIterable | None = None


class Contact(MsgSeg):
    """联系人消息段"""

    type: Literal["friend", "group"]
    id: Annotated[str, BeforeValidator(str)] | None


class Location(MsgSeg):
    """位置消息段"""

    lat: float
    lon: float
    title: str | None = None
    content: str | None = None


class Music(MsgSeg):
    """定制音乐消息段
    
    Attributes:
        id: 音乐在音乐平台的 ID。
        audio: 音频链接。
        url: 跳转链接。
        image: 封面图源，可以为路径或链接。
    """

    id: NoneType = Field(None, init=False)
    audio: str | None = None
    url: str
    title: str | None = None
    image: str | Path | AsyncIterable
    content: str | None = None


class Reply(MsgSeg):
    """回复消息段"""

    id: str


class Forward(MsgSeg):
    """转发消息段"""

    id: str | None = None
    content: Annotated[MessageChain[Node], BeforeValidator(MessageChain.from_pydantic)] | None = None
    message_type: Literal["group", "private"] | None = Field(default=None, exclude=True, repr=False)

    bot_id: int | None = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="after")
    def set_msg_type(self):
        if self.content:
            self.message_type = (
                "group" if sum(bool(node.nickname) for node in self.content) > 2 else self.message_type or "private"
            )
        return self

    async def get_content(self, bot_id: int = None):
        from core.api import API

        self.content = (await API.get_forward_msg(self.id, bot=bot_id or self.bot_id)).content
        return self.content

    def filter(self, cls: type):
        result = MessageChain(bot_id=self.bot_id)
        for node in self.content:
            result.extend(node.content.filter(cls))
        return result

    @staticmethod
    async def _get_info(user_id, nickname, bot_id):
        from core.api import API

        info = None
        if user_id is None:
            user_id = (info := await API.get_login_info(bot=bot_id)).user_id
        if nickname is None:
            nickname = (info or await API.get_login_info(bot=bot_id)).nickname
        return user_id, nickname

    async def append(
        self,
        content: Iterable[str | MsgSeg] | str | MsgSeg,
        user_id: str | int = None,
        nickname: str = None,
        bot_id: int = None,
    ):
        """
        Args:
            nickname: 若外部已拥有或欲调用多次该方法可以传入 `user_id` 和 `nickname` 参数以减少 API 调用次数。
            bot_id: 未传入 `user_id` 或 `nickname` 时调用 `get_login_info` API 的 bot 实例。默认从实例来源 bot 或当前上下文中获取。
        """
        user_id, nickname = await self._get_info(user_id, nickname, bot_id or self.bot_id)
        self.content.append(Node(user_id=user_id, nickname=nickname, content=content))

    async def extend(
        self,
        content: Iterable[Iterable[str | MsgSeg] | str | MsgSeg],
        user_id: str | int = None,
        nickname: str = None,
        bot_id: int = None,
    ):
        """
        Args:
            nickname: 若外部已拥有或欲调用多次该方法可以传入 `user_id` 和 `nickname` 参数以减少 API 调用次数。
            bot_id: 未传入 `user_id` 或 `nickname` 时调用 `get_login_info` API 的 bot 实例。默认从实例来源 bot 或当前上下文中获取。
        """
        user_id, nickname = await self._get_info(user_id, nickname, bot_id or self.bot_id)
        self.content.extend(Node(user_id=user_id, nickname=nickname, content=msg) for msg in content)

    @classmethod
    async def from_content(
        cls,
        content: Iterable[Iterable[str | MsgSeg] | str | MsgSeg],
        user_id: str | int = None,
        nickname: str = None,
        message_type: Literal["group", "private"] = None,
        bot_id: int = None,
    ):
        """
        Args:
            nickname: 若外部已拥有或欲调用多次该方法可以传入 `user_id` 和 `nickname` 参数以减少 API 调用次数。
            bot_id: 未传入 `user_id` 或 `nickname` 时调用 `get_login_info` API 的 bot 实例。默认从当前上下文中获取。
        """
        user_id, nickname = await cls._get_info(user_id, nickname, bot_id)
        return cls(
            content=MessageChain(Node(user_id=user_id, nickname=nickname, content=msg) for msg in content),
            message_type=message_type,
        )


class Node[T: MsgSeg](MsgSeg):
    """合并转发节点消息段，用于为消息绑定来源"""

    user_id: Annotated[str, BeforeValidator(str)] | None = None
    nickname: str
    content: Annotated[MessageChain[T], BeforeValidator(MessageChain.from_pydantic)]

    @field_validator("content")
    @classmethod
    def validate_content(cls, v):
        if any(isinstance(i, Node) for i in v):
            raise ValueError("Node content cannot contain Node.")
        return v


class Json(MsgSeg):
    """JSON消息段"""

    data: Annotated[dict | list, BeforeValidator(loads)]


class Xml(MsgSeg):
    """Xml消息段"""

    data: Annotated[_Element, BeforeValidator(XML)]

    @field_serializer("data")
    def serialize(self, value: _Element, _):
        return value.tostring()


class Markdown(MsgSeg):
    """Markdown消息段"""

    content: str
