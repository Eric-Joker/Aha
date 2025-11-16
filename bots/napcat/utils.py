
from collections.abc import Iterable
from functools import partial
from multiprocessing import current_process
from re import compile

from anyio import Path
from pydantic import Field, field_serializer, field_validator

from models.exc import ContentNotAccessedError, UnknownMessageTypeError
from models.msg import At as AhaAt
from models.msg import Contact as AhaContact
from models.msg import CustomMusic, Downloadable, Face, File, Forward, Image, MsgSeg, MsgSeq, Node, Record, Share, Text, Video
from utils.string import unescape_aha
from utils.typekit import AsyncBase64Encoder


class At(AhaAt):
    user_id: str | None = Field(None, validation_alias="qq", serialization_alias="qq")


class Contact(AhaContact):
    @field_validator("type", mode="before")
    @classmethod
    def validate_value(cls, v):
        return "friend" if v == "qq" else v

    @field_serializer("type")
    def serialize_value(self, v, _):
        return "qq" if v == "friend" else v


CQ_PATTERN = compile(r"\[(?:CQ|Aha):([^,\]]+)(?:,([^\]]+))?\]")


class Utils:
    @staticmethod
    def parse_cq_code_to_onebot11(cq_string):
        """将 CQ 码字符串解析为 OneBot 11 规范的消息数组格式

        Args:
            cq_string: 包含 CQ 码的字符串

        Returns:
            OneBot 11 规范的消息数组
        """

        message_segments = []
        last_pos = 0
        # 遍历所有匹配的 CQ 码
        for match in CQ_PATTERN.finditer(cq_string):
            # 处理 CQ 码之前的文本
            if text_before := cq_string[last_pos : match.start()]:
                message_segments.append({"type": "text", "data": {"text": unescape_aha(text_before)}})

            # 解析 CQ 码参数
            params = {}
            for param in (match[2] or "").split(","):
                if "=" in param:
                    key, value = param.split("=", 1)
                    params[key] = unescape_aha(value)

            message_segments.append({"type": match[1], "data": params})
            last_pos = match.end()

        # 处理最后一个 CQ 码之后的文本
        if text_after := cq_string[last_pos:]:
            message_segments.append({"type": "text", "data": {"text": unescape_aha(text_after)}})

        return message_segments

    @staticmethod
    async def prepare_file(i: str | Path, local_srv: bool):
        """将可上传对象转换为路径 或 标准 URI 或 base64 流"""
        if isinstance(i, str) and i.startswith(("http://", "https://")):
            return i
        if not await (path := Path(i)).exists():
            return (await path.resolve()).as_uri()

        if local_srv:
            return str(await path.resolve())

        if current_process().name == "MainProcess":
            from core.config import cfg

            buffer = cfg.base64_buffer
        else:
            from bots import status

            buffer = status["base64_buffer"]

        return AsyncBase64Encoder(i, buffer)

    def _convert_downloadable_dict(self, item: dict[str, dict], type_: Downloadable | Share | CustomMusic):
        data = item["data"]
        data["name"] = data["file"]
        data["file"] = data.pop("url", None)
        (obj := type_.model_validate(data)).prepare_file = partial(self.prepare_file, local_srv=self.transport.local_srv)
        return obj

    def build_message_segment(self, item: dict | MsgSeg):
        """处理为消息段"""
        if isinstance(item, MsgSeg):
            if isinstance(item, AhaAt) and not isinstance(item, At):
                return At.model_construct(**item.model_dump())
            elif isinstance(item, AhaContact) and not isinstance(item, Contact):
                return Contact.model_construct(**item.model_dump())
            elif isinstance(item, Image) and item.summary is None:
                item.summary = "[图片]"
            if hasattr(item, "prepare_file"):
                item.prepare_file = partial(self.prepare_file, local_srv=self.transport.local_srv)
            return item

        match event_type := item.get("type"):
            case "at":
                return At.model_validate(item["data"])
            case "contact":
                return Contact.model_validate(item["data"])
            case "image":
                return self._convert_downloadable_dict(item, Image)
            case "file":
                return self._convert_downloadable_dict(item, File)
            case "record":
                return self._convert_downloadable_dict(item, Record)
            case "video":
                return self._convert_downloadable_dict(item, Video)
            case _:
                obj = MsgSeq.get_class_by_name(event_type).model_validate(item["data"])
                if hasattr(obj, "prepare_file"):
                    obj.prepare_file = partial(self.prepare_file, local_srv=self.transport.local_srv)
                return obj

    def build_message_chain(self, item: MsgSeg | dict | str | Iterable | None):
        if item is None:
            return MsgSeq()

        if isinstance(item, (dict, MsgSeg)):
            return MsgSeq(self.build_message_segment(item))

        if isinstance(item, str):
            # 字符串当作CQ码处理
            return MsgSeq((self.build_message_segment(segment) for segment in self.parse_cq_code_to_onebot11(item)))

        # 处理可迭代对象
        if isinstance(item, Iterable):
            chain = MsgSeq()
            for sub_item in item:
                if isinstance(sub_item, str):
                    chain.extend(self.build_message_segment(segment) for segment in self.parse_cq_code_to_onebot11(sub_item))
                else:
                    chain.append(self.build_message_segment(sub_item))
            return chain

        raise UnknownMessageTypeError(type(item))

    # endregion
    # region 合并转发消息处理
    @classmethod
    def get_summary(cls, msg: MsgSeg):
        if isinstance(msg, Image):
            return msg.summary or "[图片]"
        if isinstance(msg, Text):
            return msg.text
        if isinstance(msg, Face):
            return msg.faceText
        if isinstance(msg, File):
            return f"[文件]{msg.get_file_name()}"
        if isinstance(msg, Record):
            # TODO: 详细解析(秒数)
            return "[语音]"
        if isinstance(msg, Video):
            return "[视频]"
        if isinstance(msg, Node):
            return f"{msg.nickname}: {"".join(cls.get_summary(m) for m in msg.content)}"
        return "[聊天记录]" if isinstance(msg, Forward) else "该消息不支持预览"

    async def to_forward_dict(self, forward: Forward | Node, is_root=True):
        if forward.content is None:
            raise ContentNotAccessedError("合并转发消息内容不存在，需先调用 `get_content()`。")

        messages = []
        nicknames = []
        for seg in forward.content:
            nicknames.append(seg.nickname)
            if isinstance(node := seg.content[0], Node):
                msg_data = await self.to_forward_dict(node, False)
                msg_data["user_id"] = node.user_id
                msg_data["nickname"] = node.nickname
                messages.append({"type": "node", "data": msg_data})
            else:
                messages.append(await self.build_message_segment(seg).serialize())

        nicknames = tuple(dict.fromkeys(nicknames))
        return {
            "messages" if is_root else "content": messages,
            "news": [{"text": self.get_summary(msg)} for msg in forward.content][:4],
            "prompt": "[聊天记录]",
            "summary": f"查看{len(forward.content)}条聊天记录",
            "source": (
                "群聊的聊天记录"
                if forward.message_type == "group" or len(nicknames) > 2
                else f"{nicknames[0]}{'' if len(nicknames) == 1 else f'和{nicknames[-1]}'}的聊天记录"
            ),
        }

    def content2forward(self, msg_id, content: list[dict]):
        return Forward(id=msg_id, content=self.build_message_chain((self.event2node(msg_event) for msg_event in content)))

    def event2node(self, data: dict[str, list[dict[str, dict]]]):
        if (message_data := data.get("message")) and message_data[0].get("type") == "forward":
            content = self.content2forward(message_data[0].get("data").get("id"), message_data[0].get("data").get("content"))
        else:
            content = message_data
        return Node(
            user_id=data.get("user_id"), nickname=data.get("sender").get("nickname"), content=self.build_message_chain(content)
        )

    # endregion
    async def long_or_forword(self, msg: MsgSeq):
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

            user_id, nick = (meta := await self.get_login_info(self.gen_id())).user_id, meta.nickname
            return Forward(content=MsgSeq(Node(user_id=user_id, nickname=nick, content=MsgSeq(s)) for s in result))
