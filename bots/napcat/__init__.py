
from asyncio import Future, get_running_loop, wait_for
from collections import deque
from time import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from orjson import loads

from core.deduplicator import FuzzyDeduplicator
from core.transports import WebSocketClient
from models.api import Message, MessageSent, MetaEvent, Notice, NoticeEventType, Request
from models.core import EventCategory
from models.exc import APIException
from models.msg import CustomMusic, MsgSeq, Share
from utils.typekit import stream_async_json

from ..base import BaseBot
from .apis import AccountAPI, GroupAPI, MessageAPI, PrivateAPI, SupportAPI
from .utils import Utils

MUSIC_PLATFORM_MAP = { # TODO: 补齐
    "163": "163",  # 不知道
    "QQ音乐": "qq",
    "kugou": "kugou",  # 不知道
    "migu": "migu",  # 不知道
    "kuwo": "kuwo",  # 不知道
}


class NapCat(AccountAPI, GroupAPI, MessageAPI, PrivateAPI, SupportAPI, Utils, BaseBot):
    platform = "QQ"
    transport_class = WebSocketClient
    deduplicator = FuzzyDeduplicator

    def __init__(self, *args, **kwargs):
        self._call_handlers: dict[str, Future] = {}
        self._notice_deque = deque()
        super().__init__(*args, **kwargs)

    @property
    def _transport_kwargs(self) -> dict:
        existing_params = dict(parse_qsl((parsed := urlparse(self.config["uri"])).query))
        existing_params["access_token"] = self.config.pop("token")
        self.config["uri"] = urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(existing_params), parsed.fragment)
        )
        #self.config["retry_config"] = {
        #}
        return self.config

    def _msg_event_processor(self, data: dict[str, str | Any]):
        data["message"] = chain = self.build_message_chain(data["message"])
        if chain and (share_data := getattr(chain[0], "data", None)) and (bizsrc := share_data.get("bizsrc")):
                        match bizsrc:
                            case "qqconnect.sdkshare_music":
                                meta = share_data["meta"]["music"]
                                data["message"] = MsgSeq(
                                    CustomMusic(
                                        type=MUSIC_PLATFORM_MAP.get(meta.get("tag")),
                                        url=meta.get("jumpUrl"),
                                        audio=meta.get("musicUrl"),
                                        title=meta.get("title"),
                                        image=meta.get("preview"),
                                        content=meta.get("desc"),
                                    )
                                )
                            case "qqconnect.sdkshare":
                                meta = share_data["meta"]["news"]
                                data["message"] = MsgSeq(
                                    Share(
                                        url=meta.get("jumpUrl"),
                                        title=meta.get("title"),
                                        content=meta.get("desc"),
                                        image=meta.get("preview"),
                                    )
                                )
        data.pop("raw_message")
        return data

    async def _listen_callback(self, data):
        self.logger.debug(f"Raw event received: {data}")

        if (echo := (data := loads(data)).get("echo")) is None:
            if type_ := data.get("post_type"):
                match type_:
                    case "message":
                        self._msg_event_processor(data)
                        cat, data = EventCategory.CHAT, Message.model_validate(data)
                    case "notice":
                        now = time()
                        cat, data = EventCategory.NOTICE, Notice.model_validate(data)

                        # 作者在 go-cqhttp 时期经历了一次“全部已进群群员莫名全都触发了一次进群事件”，导致了不可逆的影响。
                        # 由于心理阴影，故添加如下逻辑。
                        if data.event_type is NoticeEventType.GROUP_INCREASE:
                            while self._notice_deque and self._notice_deque[0] < now - 10:
                                self._notice_deque.popleft()
                            if len(self._notice_deque) >= 5:
                                exit()
                            self._notice_deque.append(now)
                    case "request":
                        cat, data = EventCategory.REQUEST, Request.model_validate(data)
                    case "meta_event":
                        cat, data = EventCategory.META, MetaEvent.model_validate(data)
                    case "message_sent":
                        self._msg_event_processor(data)
                        cat, data = EventCategory.SENT, MessageSent.model_validate(data)
                data.bot_id, data.platform, data.api_type = self.bot_id, self.platform, self.__class__.__name__
                await self.event_post(cat, data)
                self.logger.aha_debug(f"Event received: {data}")
                return
            else:
                self.logger.error(f"预期外的 API 会报且视为 FATAL:\n{data}")
                await self.close()

        if (future := self._call_handlers.get(echo)) is not None and not future.done():
            future.set_result(data)

    async def _call_api(self, echo, action, params=None, timeout=300):
        future = self._call_handlers[echo] = get_running_loop().create_future()
        await self.transport.invoke(stream_async_json({"action": action, "params": params or {}, "echo": echo}))
        try:
            data: dict = await wait_for(future, timeout)
            if (retcode := data["retcode"]) == 0:
                return data.get("data")
            raise APIException(f"请求 {action} API 失败 {retcode}:\n{data["message"]}")
        finally:
            del self._call_handlers[echo]
