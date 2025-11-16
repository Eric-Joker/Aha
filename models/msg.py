# 本文件修改自 https://github.com/liyihao1110/ncatbot

import os
from asyncio import to_thread
from collections.abc import AsyncIterable, Callable, Coroutine, Iterable
from logging import getLogger
from multiprocessing import current_process
from re import escape
from types import NoneType
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, Literal, SupportsIndex, dataclass_transform, overload
from urllib.parse import urlparse

from aiofiles import open
from anyio import Path
from httpx import HTTPStatusError
from lxml.etree import XML, _Element
from orjson import loads
from pydantic import BeforeValidator, Field, GetCoreSchemaHandler, field_validator, model_validator
from pydantic._internal._model_construction import ModelMetaclass
from pydantic_core import core_schema
from xxhash import xxh3_64_intdigest

from core.i18n import _
from models.exc import APIException, UnknownMessageTypeError
from utils.string import escape_aha
from utils.typekit import Strable

from .base import BaseModelConfig

if TYPE_CHECKING:
    from PIL.Image import Image as PilImage
    from pydantic.fields import Field as PydanticModelField
    from pydantic.fields import PrivateAttr as PydanticModelPrivateAttr
    from pydantic._internal._model_construction import NoInitField
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

    def prefixed_re_group(cls: type, prefix: Strable):
        if issubclass(cls, Text):
            return rf"(?P<{prefix}text>[^\[]+)"
        if issubclass(cls, (Forward, Node)):
            raise NotImplementedError(_("models.msg.cls2pattern.forward501"))
        return rf"\[Aha:{cls.__name__.lower()}{"".join(rf"(?:,{n}=(?P<{prefix}{n}>[\s\S]*?))?" for n, i in cls.model_fields.items() if not i.exclude)}\]"


class MsgSeg(BaseModelConfig, metaclass=MsgSegMeta):
    """消息段基类"""

    async def serialize(self):
        """转换为字典格式，排除空值和None字段"""
        data = {}
        for k, v in self.model_dump(by_alias=True, exclude_none=True).items():
            if type(v) is list and (chain := getattr(self, k, None)) and isinstance(chain, MessageChain):
                data[k] = [await seg.serialize() for seg in chain]
            elif v:
                data[k] = v

        return {"type": self.__class__.__name__.lower(), "data": data}

    def __str__(self):
        strings = [f"[Aha:{self.__class__.__name__.lower()}"]
        for k, v in self.model_dump(by_alias=True, exclude_none=True).items():
            if type(v) is list and (chain := getattr(self, k, None)) and isinstance(chain, MessageChain):
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
    def __init__(self, *elements: str | MsgSeg) -> None: ...

    @overload
    def __init__(self, iterable: Iterable[str | MsgSeg], /) -> None: ...

    def __init__(self, *args):
        if not args:
            super().__init__()
        elif len(args) == 1:
            if isinstance(arg := args[0], str):
                super().__init__((Text(text=arg),))
            elif isinstance(arg, MsgSeg):
                super().__init__(args)
            else:
                super().__init__(a if isinstance(a, MsgSeg) else Text(text=a) for a in arg)
        else:
            super().__init__(Text(text=arg) if isinstance(arg, str) else arg for arg in args)

    def __str__(self):
        return "".join(str(item) for item in self)

    def __repr__(self):
        return self.__str__()

    @classmethod
    def from_pydantic(cls, value):
        return cls(value)

    async def serialize(self) -> list[dict]:
        return [await item.serialize() for item in self]

    def add_image(self, image: str):
        """添加图片消息"""
        return self.append(Image(file=image))

    def add_at(self, user_id: str | int):
        """添加@消息"""
        return self.append(At(user_id=user_id))

    def add_reply(self, message_id: str | int):
        """添加回复消息"""
        return self.append(Reply(id=message_id))

    def prepand_image(self, image: str):
        """在列表前端添加图片消息"""
        return self.insert(0, Image(file=image))

    def prepand_at(self, user_id: str | int):
        """在列表前端添加@消息"""
        return self.insert(0, At(user_id=user_id))

    def prepand_reply(self, message_id: str | int):
        """在列表前端添加回复消息"""
        return self.insert(0, Reply(id=message_id))

    def extend(self, iterable: Iterable[T | str]):
        super().extend(Text(text=i) if isinstance(i, str) else i for i in iterable)

    def append(self, item: T | str):
        super().append(Text(text=item) if isinstance(item, str) else item)

    def insert(self, index: SupportsIndex, item: T | str):
        super().insert(index, Text(text=item) if isinstance(item, str) else item)

    def __add__(self, other: MessageChain):
        return MessageChain(super().__add__(other))

    def __radd__(self, other: MessageChain):
        return self.__add__(other)

    def copy(self):
        return MessageChain(super().copy())

    async def plain_forward_msg(self, bot: int = None):
        """把转发id格式的消息展平为解析完毕的 Forward。该方法不得用于 API 层"""
        assert isinstance(forward := self[0], Forward)
        from core.api import API

        return await API.get_forward_msg(forward.id, bot=bot)

    def filter(self, cls: type[MsgSeg] | None = None):
        """过滤特定类型的消息段"""
        if cls is None:
            return self.copy()
        return MessageChain(item for item in self if isinstance(item, cls))

    def filter_text(self) -> MessageChain[Text]:
        """过滤文本消息"""
        return self.filter(Text)

    def filter_at(self) -> MessageChain[At]:
        """过滤@消息"""
        return self.filter(At)

    def filter_image(self) -> MessageChain[Image]:
        """过滤图片消息"""
        return self.filter(Image)

    def filter_video(self) -> MessageChain[Video]:
        """过滤视频消息"""
        return self.filter(Video)

    def filter_face(self) -> MessageChain[Face]:
        """过滤表情消息"""
        return self.filter(Face)

    def is_user_at(self, user_id: str | int, include_all=False):
        """检查是否@了指定用户"""
        user_id = str(user_id)
        return any(
            (isinstance(item, At) and item.user_id == user_id) or (include_all and item.user_id == "all") for item in self
        )

    @classmethod
    def get_class_by_name(cls, name: str) -> type[MsgSeg]:
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
    """可下载消息段基类

    Attributes:
        files: 可为本地文件路径、HTTP(s) URL。
    """

    file: str | Path | AsyncIterable | None = None
    name: str = None
    thumb: str | None = None

    file_type: str | None = Field(None, init=False)
    file_size: int | None = Field(None, init=False)

    prepare_file: Callable[[str], Coroutine[Any, Any, str | AsyncIterable]] = Field(None, exclude=True, repr=False, init=False)

    async def serialize(self):
        if self.prepare_file:
            if current_process().name == "MainProcess":
                return await MsgSeg.serialize(self.model_copy(update={"file": await self.prepare_file(self.file)}))
            self.file = await self.prepare_file(self.file)  # 传递给子进程时已经 Pickle/UnPickle 一遍了。
        return await super().serialize()

    @model_validator(mode="after")
    def valid_name(self):
        if not self.name:
            self.get_file_name()
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

    async def download(self, dir_: str | Path = None, name: str | None = None) -> Path:
        """下载文件

        指定 `dir_` 时，将文件保存到指定目录，覆盖同名文件，并返回保存路径。

        未指定 `dir_` 时，若文件为本地路径，则直接返回路径；否则返回缓存文件路径。
        
        Raises:
            models.exc.APIException: 下载时出现 HTTP 错误。
        """
        if not self.file:
            raise ValueError("No downloadable URL available.")
        if not name:
            name = self.name
        if dir_:
            dir_ = Path(dir_)

        # 源文件就是本地文件
        if await (path := Path(self.file)).exists():
            return await path.copy(dir_ / name) if dir_ else path

        # 在标准文件缓存的远程文件
        from core.config import cfg

        if not dir_ and await (path := Path(cfg.get_config("cache_file_path", module="cache")) / name).exists():
            return path

        # 下载远程文件
        from utils.network import get_httpx_client

        async with get_httpx_client().stream("GET", self.file) as response:
            try:
                response.raise_for_status()
            except HTTPStatusError as e:
                raise APIException(_("models.msg.downloadable.http_error") % e) from e
            
            if dir_:
                async with open(path := dir_ / name, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        await f.write(chunk)
                return path
            from services.file_cache import cfm

            return await cfm.cache_file(cfg.file_msg_ttl, name, response.aiter_bytes())


class Text(MsgSeg):
    """纯文本消息段"""

    text: str

    def __str__(self):
        return escape_aha(self.text)

    def __repr__(self):
        return repr(self.text)

    def __eq__(self, other):
        return self.text == other if isinstance(other, str) else NotImplemented

    def __hash__(self):
        return xxh3_64_intdigest(self.text)


class MFace(MsgSeg):
    emoji_package_id: Annotated[str, BeforeValidator(str)] | None = None
    emoji_id: Annotated[str, BeforeValidator(str)] | None = None
    key: str | None = None
    summary: str | None = None


class Face(MsgSeg):
    """表情消息段"""

    id: str | None = None


class Image(Downloadable):
    """图片消息段"""

    summary: str | None = None
    sub_type: Any | None = None

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
        from services.file_cache import cfm

        await to_thread(image.save, path := await cfm.cache_file(ttl, _level=3), format=format_)
        return cls(file=path, name=name or path.name, summary=summary)


class File(Downloadable):
    """文件消息段"""

    async def serialize(self):
        (dict_data := await super().serialize())["data"]["name"] = self.get_file_name()
        return dict_data


class Record(Downloadable):
    """语音消息段"""


class Video(Downloadable):
    """视频消息段"""


class At(MsgSeg):
    """@消息段"""

    user_id: Annotated[str, BeforeValidator(str)] | None = None
    name: str | None = None

    @classmethod
    def all(cls) -> At:
        return At(user_id="all")

    def is_all(self) -> bool:
        return self.user_id == "all"


class Rps(MsgSeg):
    """猜拳消息段"""


class Dice(MsgSeg):
    """骰子消息段"""


class Shake(MsgSeg):
    """戳一戳消息段"""


class Poke(MsgSeg):
    """戳一戳消息段"""

    id: str


class Anonymous(MsgSeg):
    """匿名消息段"""


class Share(MsgSeg):
    """分享消息段"""

    url: str
    title: str | None = None
    content: str | None = None
    image: str | Path | AsyncIterable | None = None

    prepare_file: Callable[[str], Coroutine[Any, Any, str | AsyncIterable]] = Field(None, exclude=True, repr=False, init=False)

    async def serialize(self):
        if self.prepare_file:
            if current_process().name == "MainProcess":
                return await MsgSeg.serialize(self.model_copy(update={"image": await self.prepare_file(self.image)}))
            self.image = await self.prepare_file(self.image)
        return await super().serialize()


class Contact(MsgSeg):
    """联系人消息段"""

    type: Literal["friend", "group"]
    id: Annotated[str, BeforeValidator(str)] | None


class Location(MsgSeg):
    """位置消息段"""

    lat: float
    lon: float
    title: str = "Location Share"
    content: str | None = None


class Music(MsgSeg):
    """音乐消息段"""

    type: Any | str | Literal["qq", "163", "kugou", "migu", "kuwo"] | None = None
    id: Annotated[str, BeforeValidator(str)]

    @model_validator(mode="wrap")
    @classmethod
    def custom(cls, values: dict, handler):
        return CustomMusic.model_validate(values) if values.get("type") == "custom" else handler(values)


class CustomMusic(Music):
    type: Any | str | Literal["qq", "163", "kugou", "migu", "kuwo", "custom"] = "custom"
    id: NoneType = None
    audio: str | None = None  # 媒体链接
    url: str  # 跳转链接
    title: str | None = None
    image: str | Path | AsyncIterable
    content: str | None = None

    prepare_file: Callable[[str], Coroutine[Any, Any, str | AsyncIterable]] = Field(None, exclude=True, repr=False, init=False)

    async def serialize(self):
        if self.prepare_file:
            if current_process().name == "MainProcess":
                return await MsgSeg.serialize(self.model_copy(update={"image": await self.prepare_file(self.image)}))
            self.image = await self.prepare_file(self.image)
        return await super().serialize()


class Reply(MsgSeg):
    """回复消息段"""

    id: str


class Node(MsgSeg):
    """合并转发节点消息段"""

    user_id: Annotated[str, BeforeValidator(str)] | None = None
    nickname: str
    content: Annotated[MessageChain | str | MsgSeg, BeforeValidator(MessageChain.from_pydantic)] | None = None

    @field_validator("content")
    @classmethod
    def forward2node(cls, value: MessageChain[Forward | MsgSeg]):
        for i, seg in enumerate(value):
            if isinstance(seg, Forward):
                value[i] = seg.content[0]
        return value


class Forward(MsgSeg):
    """转发消息段"""

    id: str | None = None
    message_type: Literal["group", "friend"] | None = None
    content: Annotated[MessageChain[Node], BeforeValidator(MessageChain.from_pydantic)] | None = None

    async def get_content(self, bot: int = None):
        from core.api import API

        self.content = (await API.get_forward_msg(self.id, bot=bot)).content
        return self.content

    def filter(self, cls: type):
        return self.content[0].content.filter(cls) if self.content else MessageChain()

    def append(self, content: MessageChain, user_id: str | int, nickname: str):
        self.content.append(Node(user_id=user_id, nickname=nickname, content=content))


class Json(MsgSeg):
    """JSON消息段"""

    data: Annotated[dict | list, BeforeValidator(loads)]


class Xml(MsgSeg):
    """Xml消息段"""

    data: Annotated[_Element, BeforeValidator(XML)]


class Markdown(MsgSeg):
    """Markdown消息段"""

    content: str
