from collections import deque
from time import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from orjson import loads

import core.status
from core.deduplicator import FuzzyDeduplicator
from core.transports import WebSocketClient
from models.api import Message, MessageSent, MetaEvent, Notice, NoticeEventType, Request
from models.core import EventCategory

from ..base import BaseBot
from .apis import AccountAPI, GroupAPI, MessageAPI, PrivateAPI, SupportAPI
from .utils import (
    AICharacter,
    AICharacterList,
    GroupInfo,
    GroupMemberInfo,
    GroupMembers,
    GroupHonor,
    GroupHonorUser,
    HonorType,
    sticker2cq_face,
)

__all__ = (
    "NapCat",
    "sticker2cq_face",
    "GroupInfo",
    "GroupMemberInfo",
    "GroupMembers",
    "GroupHonor",
    "GroupHonorUser",
    "HonorType",
    "AICharacter",
    "AICharacterList",
)


class NapCat(AccountAPI, GroupAPI, MessageAPI, PrivateAPI, SupportAPI, BaseBot):
    platform = "QQ"
    transport_class = WebSocketClient
    deduplicator = FuzzyDeduplicator

    def __init__(self, bot_id, config, pipe=None):
        super().__init__(bot_id, config, pipe)
        if limit_config := self.config.pop("limit_group_increase", None):
            self._gi_window = limit_config[0]
            self._gi_deque = deque(maxlen=limit_config[1])
        else:
            self._gi_deque = None

    @property
    def _transport_kwargs(self) -> dict:
        existing_params = dict(parse_qsl((parsed := urlparse(self.config["uri"])).query))
        existing_params["access_token"] = self.config.pop("token")
        self.config["uri"] = urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(existing_params), parsed.fragment)
        )
        if d := self.config.get("retry_config"):
            self.config["retry_config"] = self.parse_retry_config(d)
        return self.config

    async def _listen_callback(self, data):
        self.logger.debug(f"Raw received: {data}")

        if (echo := (data := loads(data)).get("echo")) is None:
            if type_ := data.pop("post_type", None):
                match type_:
                    case "message":
                        await self._msg_event_processor(data)
                        cat, data = EventCategory.CHAT, Message.model_validate(data)
                    case "notice":
                        now = time()
                        if data["notice_type"] == "group_msg_emoji_like":
                            data["notice_type"] = NoticeEventType.REACTION
                        cat, data = EventCategory.NOTICE, Notice.model_validate(data)

                        # 作者在 go-cqhttp 时期经历了一次“全部已进群群员莫名全都触发了一次进群事件”，导致了不可逆的影响。
                        # 由于心理阴影，故添加如下逻辑。
                        if self._gi_deque and data.event_type is NoticeEventType.GROUP_INCREASE:
                            while self._gi_deque and self._gi_deque[0] < now - self._gi_window:
                                self._gi_deque.popleft()
                            if len(self._gi_deque) == self._gi_deque.maxlen:
                                self.logger.error(
                                    f"疑似QQ发癫啦！{self._gi_window}秒钟收到了{self._gi_deque.maxlen}次入群消息！强制退出！"
                                )
                                core.status.main_task.cancel()
                            self._gi_deque.append(now)
                    case "request":
                        cat, data = EventCategory.REQUEST, Request.model_validate(data)
                    case "meta_event":
                        cat, data = EventCategory.META, MetaEvent.model_validate(data)
                    case "message_sent":
                        await self._msg_event_processor(data)
                        cat, data = EventCategory.SENT, MessageSent.model_validate(data)
                await self.event_post(cat, data)
                self.logger.aha_debug(f"Event received: {data}")
                return
            else:
                self.logger.error(f"预期外的 API 上报且视为 FATAL:\n{data}")
                await self.close()

        if (future := self._call_handlers.get(echo)) is not None and not future.done():
            future.set_result(data)
