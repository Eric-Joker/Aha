import signal
import sys
from asyncio import create_task, get_running_loop, sleep
from contextlib import suppress
from typing import Any, Literal, overload

from tenacity.stop import stop_base
from tenacity.wait import wait_base

import core.status
from core.deduplicator import Deduplicator
from core.i18n import _, load_locales
from core.log import setup_logging
from core.transports import ClientTransport, Transport
from models.api import BaseEvent, LifecycleSubType, MetaEvent, MetaEventType
from models.core import EventCategory
from models.metas import PerProcessSingletonMeta
from utils.aio import AsyncConnection, run_with_uvloop
from utils.typekit import make_exc_picklable

from .apis import BaseAccountAPI, BaseGroupAPI, BaseMessageAPI, BasePrivateAPI, BaseSupportAPI

RetryConfigKey = Literal[
    "stop_any",
    "stop_all",
    "stop_after_attempt",
    "stop_after_delay",
    "stop_before_delay",
    "wait_fixed",
    "wait_random",
    "wait_incrementing",
    "wait_exponential",
    "wait_random_exponential",
    "wait_exponential_jitter",
    "wait_chain",
    "wait_combine",
]


def api_process(bot_class: type[BaseBot], bot_id, pipe, config, base64_buffer, lang, log):
    setup_logging(log)
    core.status.base64_buffer = base64_buffer
    core.status.def_lang = lang

    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if sys.platform == "win32":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)

    with suppress(KeyboardInterrupt):
        run_with_uvloop(_run(bot_class(bot_id, config, AsyncConnection(pipe)).start()))


async def _run(coroutine):
    core.status.main_task = create_task(coroutine)
    await core.status.main_task


class BaseBotMeta(PerProcessSingletonMeta):
    """注册所有API子类"""

    def __init__(cls, name, bases, attrs):
        from core.bot_register import register

        super().__init__(name, bases, attrs)
        register(cls)


class BaseBot(BaseAccountAPI, BaseGroupAPI, BaseMessageAPI, BasePrivateAPI, BaseSupportAPI, metaclass=BaseBotMeta):
    platform: str
    transport_class: type[Transport]
    deduplicator: type[Deduplicator]

    def __init__(self, bot_id, config: dict, pipe: AsyncConnection = None):
        super().__init__()
        self.bot_id = bot_id
        self.pipe = pipe
        self.is_process_mode = pipe is not None
        self._start_server_comm = config.pop("start_server_command", None)
        self.config = config
        self.transport = (
            self.transport_class(self.logger, self._disconnect_cb, self._reconnect_cb)
            if issubclass(self.transport_class, ClientTransport)
            else self.transport_class(self.logger)
        )

    async def start(self):
        if self.is_process_mode:
            await load_locales()
            self._request_listen = create_task(self._handle_requests())

        await load_locales(self.__class__.__module__)
        try:
            await self.transport.open(**self._transport_kwargs)
        except Exception as e:
            self.logger.error(_("api.service.conn.failed") % e)
            await self.close()
            return False
        self.logger.info(_("api.service.init.success"))
        create_task(self.transport.listen(self._listen_callback)).add_done_callback(self._close)

        if self.is_process_mode:
            await get_running_loop().create_future()
        return True

    async def event_post(self, catrgory, data: BaseEvent):
        data.bot_id, data.platform, data.adapter = self.bot_id, self.platform, self.__class__.__name__
        if self.is_process_mode:
            with suppress(BrokenPipeError, EOFError):
                await self.pipe.send((catrgory, data))
        else:
            from core.api_service import event_route

            event_route(self.bot_id, catrgory, data)

    async def _handle_requests(self):
        """仅多进程模式"""
        while True:
            call_id, method, args, kwargs = await self.pipe.recv()
            try:
                await self.pipe.send((EventCategory.RESPONSE, (call_id, await getattr(self, method)(call_id, *args, **kwargs))))
            except EOFError:
                pass
            except Exception as e:
                create_task(self.pipe.send((EventCategory.RESPONSE, (call_id, make_exc_picklable(e)))))
            await sleep(0.001)

    async def close(self, _=None):  # 参数为 call_id
        await self.transport.close()
        self._close()

    def _close(self, _=None):
        if self.is_process_mode:
            self._request_listen.cancel()
            self.pipe.close()
        else:
            # TODO: 重写这里超越界限的逻辑
            from core.api_service import clean_bot

            clean_bot(self.bot_id)

    def parse_retry_config(self, config: dict[RetryConfigKey, int | float | list[dict[RetryConfigKey, Any] | Any]]):
        """解析重试策略配置，返回包含wait和stop实例的字典"""

        stop_types = {cls.__name__: cls for cls in stop_base.__subclasses__()}
        wait_types = {cls.__name__: cls for cls in wait_base.__subclasses__()}

        # 分离stop和wait配置
        stop_configs = {}
        wait_configs = {}
        for k, v in config.items():
            if k.startswith("stop_"):
                stop_configs[k] = v
            elif k.startswith("wait_"):
                wait_configs[k] = v
            else:
                self.logger.warning(_("api.service.retry_config_422") % k)

        # 配置冲突
        if len(stop_configs) > 1:
            raise ValueError(_("api.service.retry_config_409.stop"))
        if len(wait_configs) > 1:
            raise ValueError(_("api.service.retry_config_409.wait"))

        # 处理stop
        result = {}
        for stop_key, stop_value in stop_configs.items():
            stop_cls = stop_types[stop_key]

            if stop_key in ("stop_any", "stop_all"):
                # 递归
                result["stop"] = stop_cls(*[self.parse_retry_config(sub_config)["stop"] for sub_config in stop_value])
            else:
                result["stop"] = stop_cls(**stop_value)

        # 处理wait
        for wait_key, wait_value in wait_configs.items():
            wait_cls = wait_types[wait_key]

            if wait_key in ("wait_chain", "wait_combine"):
                # 递归
                result["wait"] = wait_cls(*[self.parse_retry_config(sub_config)["wait"] for sub_config in wait_value])
            else:
                result["wait"] = wait_cls(**wait_value)

        return result

    async def _disconnect_cb(self):
        await self.event_post(
            EventCategory.META, MetaEvent(event_type=MetaEventType.LIFECYCLE, sub_type=LifecycleSubType.DISCONNECT)
        )

    async def _reconnect_cb(self):
        pass

    @property
    def _transport_kwargs(self) -> dict:
        """返回用于传递给 `transport.connect` 的 kwargs"""
        raise NotImplementedError

    @overload
    async def _listen_callback(self, data): ...

    @overload
    def _listen_callback(self, data): ...

    def _listen_callback(self, data):
        """处理上报事件与API返回值"""
        raise NotImplementedError
