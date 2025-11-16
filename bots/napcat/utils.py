import os
from asyncio import Future, get_running_loop, wait_for
from collections.abc import Iterable
from contextlib import suppress
from datetime import datetime
from multiprocessing import current_process
from re import compile
from typing import TYPE_CHECKING, Annotated, Any, overload

from anyio import Path
from pydantic import BeforeValidator, Field
from websockets import State

import core.status
from bots.apis import BaseAPI
from core.transports import WebSocketClient
from models.api import GroupInfo as AhaGroupInfo
from models.api import GroupMemberInfo as AhaGroupMemberInfo
from models.api import GroupMembers as AhaGroupMembers
from models.base import FrozenBaseModel, PureNameEnum
from models.exc import APIException, UnknownMessageTypeError
from models.msg import (
    At,
    Contact,
    Downloadable,
    File,
    Forward,
    Image,
    Json,
    MsgSeg,
    MsgSeq,
    Music,
    Node,
    Record,
    Reply,
    Share,
    Sticker,
    Text,
    Video,
)
from utils.aha import aha_code2dict_list, parse_aha_code
from utils.typekit import AsyncBase64Encoder, stream_async_json

if TYPE_CHECKING:
    from . import NapCat

MUSIC_PLATFORM_MAP = {  # TODO: 补齐
    "163": "163",  # 不知道
    "QQ音乐": "qq",
    "kugou": "kugou",  # 不知道
    "migu": "migu",  # 不知道
    "kuwo": "kuwo",  # 不知道
}

CQ_CODE_PATTERN = compile(r"\[CQ:([^,\]]+)(?:,([^\]]+))?\]")


def sticker2cq_face(sticker: Sticker):
    return f"[CQ:face,id={sticker.file_id}]"


class GroupInfo(AhaGroupInfo):
    max_member_count: int | None = None


class GroupMemberInfo(AhaGroupMemberInfo):
    activity_level: str
    title_expire_time: Annotated[datetime, BeforeValidator(datetime.fromtimestamp)] = Field(
        validation_alias="specialTitleExpireTime"
    )
    card_changeable: bool


class GroupMembers(AhaGroupMembers[GroupMemberInfo]):
    def __new__(cls, *args):
        return super().__new__(cls, *args, element_cls=GroupMemberInfo)

    def filter_by_level_ge(self, level: int):
        """过滤活跃等级大于等于指定值的成员"""
        return GroupMembers(member for member in self if int(member.activity_level) >= level)

    def filter_by_level_le(self, level: int):
        """过滤活跃等级小于等于指定值的成员"""
        return GroupMembers(member for member in self if int(member.activity_level) <= level)


class HonorType(str, PureNameEnum):
    TALKATIVE = "talkative"
    PERFORMER = "performer"
    EMOTION = "emotion"


class GroupHonorUser(FrozenBaseModel):
    user_id: Annotated[str, BeforeValidator(str)]
    nickname: str
    avatar: str
    description: str | None = None


class GroupHonor(FrozenBaseModel):
    group_id: Annotated[str, BeforeValidator(str)]
    current_talkative: GroupHonorUser
    talkative_list: list[GroupHonorUser]
    performer_list: list[GroupHonorUser] = []
    legend_list: list[GroupHonorUser] = []
    emotion_list: list[GroupHonorUser] = []


class AICharacter(FrozenBaseModel):
    character_id: str
    character_name: str
    preview_url: str


class AICharacterList(list[AICharacter]):
    @overload
    def __init__(self) -> None: ...

    @overload
    def __init__(self, *elements: dict | AICharacter) -> None: ...

    @overload
    def __init__(self, iterable: Iterable[dict | AICharacter], /) -> None: ...

    def __init__(self, *args):
        if not args:
            super().__init__()
        elif len(args) == 1:
            if isinstance(arg := args[0], dict):
                super().__init__((AICharacter.model_validate(arg),))
            elif isinstance(arg, AICharacter):
                super().__init__(args)
            else:
                super().__init__(AICharacter.model_validate(a) if isinstance(a, dict) else a for a in arg)
        else:
            super().__init__(AICharacter.model_validate(arg) if isinstance(arg, dict) else arg for arg in args)

    def get_search_id_by_name(self, name: str) -> str | None:
        return next((character.character_id for character in self if character.character_name == name), None)


_poke_flag = object()


class Utils(BaseAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._call_handlers: dict[str, Future] = {}
        if TYPE_CHECKING:
            self.transport: WebSocketClient

    async def _call_api(self, echo, action, params=None, timeout=300) -> Any:
        future = self._call_handlers[echo] = get_running_loop().create_future()
        await self.transport.invoke(stream_async_json({"action": action, "params": params or {}, "echo": echo}))
        try:
            data: dict = await wait_for(future, timeout)
            if (retcode := data["retcode"]) == 0:
                return data.get("data")
            raise APIException(f"请求 {action} API 失败 {retcode}:\n{data["message"]}")
        except TimeoutError:
            if self.transport.websocket.state is not State.CLOSING and self.transport.websocket.state is not State.CLOSED:
                raise TimeoutError(f"请求 {action} API 超时 {timeout} 秒。")
        finally:
            del self._call_handlers[echo]

    async def _msg_event_processor(self, data: dict):
        if "raw" in data:
            self.logger.warning("不建议在生产环境中开启 NapCat 网络配置的调试模式，这会产生成倍的无效数据。")
        if data["message_format"] == "array":
            self._msg_event_processor = self._array_msg_event_processor
        else:
            self.logger.warning("不建议在 NapCat 的网络配置中选择 String 消息格式，这会严重降低性能。")
            self._msg_event_processor = self._string_msg_event_processor
        return await self._msg_event_processor(data)

    async def _array_msg_event_processor(self, data: dict):
        del data["raw_message"]
        del data["message_seq"]
        del data["real_id"]
        del data["sender"]["user_id"]
        del data["message_format"]
        if data["sub_type"] == "group":
            data["sub_type"] == "temporary"
        data["message"] = MsgSeq(
            [await self.build_msg_seg(item, data["user_id"], data.get("group_id")) for item in data["message"]]
        )
        return data

    async def _string_msg_event_processor(self, data: dict[str, str | Any]):
        del data["raw_message"]
        del data["message_seq"]
        del data["real_id"]
        del data["sender"]["user_id"]
        del data["message_format"]
        if data["sub_type"] == "group":
            data["sub_type"] == "temporary"
        data["message"] = MsgSeq(
            [
                await self.build_msg_seg(item, data["user_id"], data.get("group_id"))
                for item in (
                    aha_code2dict_list(data["message"], CQ_CODE_PATTERN)
                    if isinstance(data["message"], str)
                    else data["message"]
                )
            ]
        )
        return data

    # region onebot2aha
    def _build_downloadable[T: type[Downloadable] | type[Share] | type[Music]](self: NapCat, item: dict[str, dict], type_: T):
        data["name"] = (data := item["data"])["file"]
        data["file"] = data.pop("url", data["file"])
        (obj := type_.model_validate(data)).bot_id = self.bot_id
        return obj

    async def parse_forward(self: NapCat, seg_data: dict[str, Any]):
        if "content" not in seg_data:
            with suppress(APIException):
                seg_data["content"] = await self.get_forward_msg(self.gen_id(), seg_data["id"], True)

    async def build_msg_seg(self: NapCat, item: dict[str, Any | dict], uid=None, gid=None):
        """处理为消息段对象"""
        match event_type := item["type"]:
            case "at":
                data["user_id"] = (data := item["data"]).pop("qq")
                return At.model_validate(data)
            case "face":
                return Sticker(summary=(data := item["data"])["raw"]["faceText"], file_id=data["id"])
            case "image":
                if "emoji_package_id" in (data := item["data"]):
                    data["file_id"] = (data.pop("emoji_package_id"), data.pop("emoji_id"), data.pop("key"))
                    return self._build_downloadable(item, type_=Sticker)
                return self._build_downloadable(item, Image)
            case "file":
                result: File = self._build_downloadable(item, File)
                if gid:
                    result.group_id = gid
                return result
            case "record":
                return self._build_downloadable(item, Record)
            case "video":
                return self._build_downloadable(item, Video)
            case "json":
                if bizsrc := (obj := Json.model_validate(item["data"])).data.get("bizsrc"):
                    match bizsrc:
                        case "qqconnect.sdkshare":
                            meta: dict = obj.data["meta"]["news"]
                            result = Share(
                                url=meta.get("jumpUrl"),
                                title=meta.get("title"),
                                content=meta.get("desc"),
                                image=meta.get("preview"),
                            )
                            result.extra["raw"] = obj.data
                            return result
                        case "qqconnect.sdkshare_music":
                            meta: dict = obj.data["meta"]["music"]
                            result = Music(
                                type=MUSIC_PLATFORM_MAP.get(meta.get("tag")),
                                url=meta.get("jumpUrl"),
                                audio=meta.get("musicUrl"),
                                title=meta.get("title"),
                                image=meta.get("preview"),
                                content=meta.get("desc"),
                            )
                            result.extra["raw"] = obj.data
                            return result
                elif bizsrc := obj.data.get("app"):
                    match bizsrc:
                        case "com.tencent.multimsg":
                            with suppress(APIException):
                                return await self.get_forward_msg(self.gen_id(), obj.data["meta"]["detail"]["resid"])
                return obj
            case "forward":
                if "content" not in (data := item["data"]):
                    await self.parse_forward(data)
                obj = await self.content2forward(**data)
                obj.bot_id = self.bot_id
                return obj
            case "contact":
                if (data := item["data"])["type"] == "qq":
                    data["type"] = "friend"
                return Contact.model_validate(data)
            case "shake" | "poke":
                return Sticker(summary="戳一戳", file_id=(_poke_flag, item["data"].get("id", 0)))
            case _:
                return MsgSeq.get_seg_class(event_type).model_validate(item["data"])

    # region 合并转发
    async def content2forward(self: NapCat, id, content: list[dict]):
        return Forward(
            id=id,
            content=[await self.event2node(e) for e in content],
            message_type="group" if content[0].get("group_id") else "private",
            bot_id=self.bot_id,
        )

    async def event2node(self, data: dict[str, list[dict[str, dict]]]):
        if (forward := data["message"]) and (forward := forward[0])["type"] == "forward":
            content = await self.content2forward(**forward["data"])
        else:
            content = (await self._msg_event_processor(data))["message"]
        return Node(user_id=data["user_id"], nickname=data["sender"]["nickname"], content=content)

    # endregion
    # endregion
    # region aha2onebot
    @staticmethod
    async def prepare_upload(i: str | Path, local_srv: bool):
        """将可上传对象转换为路径 或 标准 URI 或 base64 流"""
        if isinstance(i, str) and i.startswith(("http://", "https://")):
            return i

        if local_srv:
            return str(await path.resolve())

        if not await (path := Path(i)).exists():
            return str(path)

        if current_process().name == "MainProcess":
            from core.config import cfg

            buffer = cfg.base64_buffer
        elif (buffer := core.status.base64_buffer) is None:
            raise RuntimeError("无法获取配置项，请勿在子进程调用该方法。")

        return AsyncBase64Encoder(i, buffer)

    async def serialize_msg_seg(self, item: MsgSeg):
        """不处理 Forward"""
        if isinstance(item, Sticker):
            if isinstance(item.file_id, tuple):
                if item.file_id[0] is _poke_flag:
                    return {"type": "poke", "data": {"id": item.file_id[1]}}
                return {
                    "type": "mface",
                    "data": {
                        "emoji_package_id": item.file_id[0],
                        "emoji_id": item.file_id[1],
                        "key": item.file_id[2],
                        "summary": item.summary,
                    },
                }
            return {"type": "face", "data": {"id": item.file_id}}
        if isinstance(item, Downloadable):
            if self.is_process_mode:
                item.file = await self.prepare_upload(item.file, self.transport.local_srv)
                return await item.serialize()
            return await item.model_copy(
                update={"file": await self.prepare_upload(item.file, self.transport.local_srv)}
            ).serialize()
        if isinstance(item, Music):
            if self.is_process_mode:
                item.image = await self.prepare_upload(item.image, self.transport.local_srv)
                return await item.serialize()
            return await item.model_copy(
                update={"image": await self.prepare_upload(item.image, self.transport.local_srv)}
            ).serialize()
        if isinstance(item, At):
            return {"type": "at", "data": {"qq": item.user_id}}
        if isinstance(item, Share):
            if raw := item.extra.get("raw"):
                meta = raw["meta"]["news"]
                if item.url:
                    meta["jumpUrl"] = item.url
                if item.title:
                    meta["title"] = item.title
                if item.content:
                    meta["desc"] = item.content
                if item.image != meta.get("preview"):
                    self.logger.warning("不支持修改 Share 消息段的 image 属性。", stack_info=True)
                return {"type": "json", "data": {"data": raw}}
            raise NotImplementedError("暂不支持发送非 QQ 来源的 Share 消息段。")
        if isinstance(item, Contact):
            return {"type": "contact", "data": {"type": "qq" if item.type == "friend" else item.type, "id": item.id}}
        return await item.serialize()

    async def serialize_msg(self, data: Iterable | MsgSeg | str | None):
        """序列化为可用于 OneBot 的 Json 数据类型。不处理 Forward"""
        if data is None:
            return []

        if isinstance(data, MsgSeg):
            return [await self.serialize_msg_seg(data)]

        if isinstance(data, str):
            return [await self.serialize_msg_seg(seg) for seg in parse_aha_code(data)]

        if isinstance(data, Iterable):
            result = []
            for item in data:
                if isinstance(item, str):
                    result.extend([await self.serialize_msg_seg(segment) for segment in parse_aha_code(item)])
                else:
                    result.append(await self.serialize_msg_seg(item))
            return result

        raise UnknownMessageTypeError((data.__class__.__qualname__))

    # region 合并转发
    @classmethod
    def get_summary(cls, msg: MsgSeg):
        if isinstance(msg, Text):
            return msg.text
        if isinstance(msg, Image):
            return msg.summary or "[图片]"
        if isinstance(msg, Video):
            return "[视频]"
        if isinstance(msg, File):
            return f"[文件]{msg.get_file_name()}"
        if isinstance(msg, Record):
            # TODO: 详细解析(秒数)
            return "[语音]"
        if isinstance(msg, Node):
            return f"{msg.nickname}: {"".join(cls.get_summary(m) for m in msg.content)}"
        if isinstance(msg, Reply):
            return ""
        return "[聊天记录]" if isinstance(msg, Forward) else "该消息不支持预览"

    async def forward2dict(self: NapCat, forward: Forward, _is_root=True):
        messages = []
        nicknames = []
        for node in forward.content:
            nicknames.append(node.nickname)
            if node.content:
                if isinstance(sub_forward := node.content[0], Forward):
                    msg_data = await self.forward2dict(sub_forward, False)
                    msg_data["user_id"] = node.user_id
                    msg_data["nickname"] = node.nickname
                    messages.append({"type": "node", "data": msg_data})
                else:
                    messages.append({"type": "node", "data": {"content": await self.serialize_msg(node.content)}})

        nicknames = tuple(dict.fromkeys(nicknames))
        return {
            "messages" if _is_root else "content": messages,
            "news": [{"text": self.get_summary(msg)} for msg in forward.content][:4],
            "prompt": "[聊天记录]",
            "summary": f"查看{len(forward.content)}条聊天记录",
            "source": (
                "群聊的聊天记录"
                if forward.message_type == "group" or len(nicknames) > 2
                else f"{nicknames[0]}{'' if len(nicknames) == 1 else f'和{nicknames[-1]}'}的聊天记录"
            ),
        }

    # endregion
    # region send_forward_msg_by_id
    @classmethod
    def get_summary_from_raw(cls, msg: dict):
        match msg["type"]:
            case "image":
                return msg["data"]["summary"] or "[图片]"
            case "text":
                return msg["data"]["text"]
            case "file":
                return f"[文件]{os.path.basename(msg['data']["file"])}"
            case "record":
                # TODO: 详细解析(秒数)
                return "[语音]"
            case "video":
                return "[视频]"
            case "node":
                return f"{(data := msg['data'])['nickname']}: {"".join(cls.get_summary_from_raw(m) for m in data['content'])}"
            case "forward":
                return "[聊天记录]"
            case _:
                return "该消息不支持预览"

    @classmethod
    def raw2forward_data(cls, content: list[dict], id=None):
        if id:
            return {
                "id": id,
                "content": [cls.event2node_raw(e) for e in content],
                "message_type": "group" if content[0].get("group_id") else "private",
            }
        return {
            "content": [cls.event2node_raw(e) for e in content],
            "message_type": "group" if content[0].get("group_id") else "private",
        }

    @classmethod
    def event2node_raw(cls, data: dict[str, list[dict[str, dict]]]):
        if (chain := data["message"]) and (forward := chain[0])["type"] == "forward":
            content = [{"type": "forward", "data": cls.raw2forward_data(**forward["data"])}]
        else:
            content = chain
        return {
            "type": "node",
            "data": {"user_id": data["user_id"], "nickname": data["sender"]["nickname"], "content": content},
        }

    def content2send_raw(self: NapCat, forward_data: dict[str, Any | list[dict]], _is_root=True):
        messages = []
        nicknames = []
        for node in forward_data["content"]:
            nicknames.append((node_data := node["data"])["nickname"])
            if content := node_data["content"]:
                if (sub_forward := content[0])["type"] == "forward":
                    msg_data = self.content2send_raw(sub_forward["data"], False)
                    msg_data["user_id"] = node_data["user_id"]
                    msg_data["nickname"] = node_data["nickname"]
                    messages.append({"type": "node", "data": msg_data})
                else:
                    messages.append(node)

        nicknames = tuple(dict.fromkeys(nicknames))
        return {
            "messages" if _is_root else "content": messages,
            "news": [{"text": self.get_summary_from_raw(msg)} for msg in forward_data["content"]][:4],
            "prompt": "[聊天记录]",
            "summary": f"查看{len(forward_data["content"])}条聊天记录",
            "source": (
                "群聊的聊天记录"
                if forward_data["message_type"] == "group" or len(nicknames) > 2
                else f"{nicknames[0]}{'' if len(nicknames) == 1 else f'和{nicknames[-1]}'}的聊天记录"
            ),
        }

    # endregion
    async def shorter_or_forward(self: NapCat, msg: MsgSeq):
        need_split = False
        image_count = 0
        for seg in msg:
            if isinstance(seg, Text):
                if len(seg.text) > 4501:
                    need_split = True
                    break
            elif isinstance(seg, Image):
                image_count += 1

        if need_split or image_count > 20:
            result = []
            for seg in msg:
                if isinstance(seg, Text) and len(seg.text) > 4501:
                    result.extend(seg.text[i : i + 4501] for i in range(0, len(seg.text), 4501))
                else:
                    result.append(seg)

            meta = await self.get_login_info(self.gen_id())
            return Forward(
                content=MsgSeq(Node(user_id=meta.user_id, nickname=meta.nickname, content=MsgSeq(s)) for s in result),
                bot_id=self.bot_id,
            )

    # endregion
