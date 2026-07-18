from asyncio import sleep
from datetime import datetime
from threading import current_thread, main_thread
from time import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

from aiologic.lowlevel import lazydeque
from ssrjson import loads

import core.status
from core.transports import WebSocketClient
from models.api import (
    Friend,
    LifecycleSubType,
    Message,
    MessageSent,
    MetaEvent,
    MetaEventType,
    Notice,
    NoticeEventType,
    Request,
)
from models.core import EventCategory

from ..base import BaseBot
from .apis import AccountAPI, GroupAPI, MessageAPI, PrivateAPI, SupportAPI
from .models.account import Stranger
from .models.group import EssenceMessage, GroupHonor, GroupHonorUser, GroupInfo, GroupMemberInfo, GroupMembers, HonorType
from .models.message import StickerType
from .models.support import AICharacter, AICharacterList
from .utils import sticker2cq_face

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
    "Friend",
    "Stranger",
    "EssenceMessage",
    "StickerType",
)


class NapCat(AccountAPI, GroupAPI, MessageAPI, PrivateAPI, SupportAPI, BaseBot):
    platform = "QQ"
    transport_class = WebSocketClient

    def __init__(self, bot_id, config, pipe=None):
        super().__init__(bot_id, config, pipe)
        self._sent_connect = False
        if limit_config := self.config.pop("limit_group_increase", None):
            self._gi_window = limit_config[0]
            self._gi_deque = lazydeque(maxlen=limit_config[1])
        else:
            self._gi_deque = None

    @classmethod
    def _get_transport_kwargs(cls, config: dict):
        existing_params = dict(parse_qsl((parsed := urlparse(config["uri"])).query))
        existing_params["access_token"] = config.pop("token")
        config["uri"] = urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(existing_params), parsed.fragment)
        )
        if d := config.get("retry_config"):
            config["retry_config"] = cls.parse_retry_config(d)
        return config

    def _listen_callback(self, data):
        if current_thread() is main_thread():
            self._listen_callback = self._process_event
        else:
            self._listen_callback = self._event_into_thread
        return self._listen_callback(data)

    def _event_into_thread(self, data):
        return core.status.async_loop_executor.submit(self._process_event, data)

    async def _process_event(self, data):
        self.logger.debug(f"Raw received: {data}")

        if (echo := (data := loads(data)).get("echo")) is None:
            if type_ := data.pop("post_type", None):
                data["time"] = datetime.fromtimestamp(int(data["time"]), ZoneInfo("Asia/Shanghai"))
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
                                await self.close()
                            self._gi_deque.append(now)
                    case "request":
                        cat, data = EventCategory.REQUEST, Request.model_validate(data)
                    case "meta_event":
                        cat, data = EventCategory.META, MetaEvent.model_validate(data)
                        if data.sub_type is LifecycleSubType.CONNECT:
                            self._sent_connect = True
                    case "message_sent":
                        await self._msg_event_processor(data)
                        cat, data = EventCategory.SENT, MessageSent.model_validate(data)
                await self.event_post(cat, data)
                self.logger.aha_debug(f"Event received: {data}")
            else:
                self.logger.error(f"预期外的 API 上报且视为 FATAL:\n{data}")
                await self.close()
            return

        if (future := self._calls.get(echo)) is not None:
            future.set_result(data)

    async def _disconnect_cb(self):
        self._sent_connect = False
        await super()._disconnect_cb()

    async def _connect_cb(self):
        await sleep(3)
        if not self._sent_connect:
            await self.event_post(
                EventCategory.META, MetaEvent(event_type=MetaEventType.LIFECYCLE, sub_type=LifecycleSubType.CONNECT)
            )
