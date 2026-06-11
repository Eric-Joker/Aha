import signal
import sys
from abc import abstractmethod
from asyncio import CancelledError, create_task, get_running_loop
from contextlib import suppress
from logging import getLogger
from typing import TYPE_CHECKING, Any, Literal, overload

from tenacity.stop import stop_base
from tenacity.wait import wait_base

import core.status
from core.i18n import _, load_locales
from core.log import AhaLogger, setup_logging
from core.transports import ClientTransport, Transport
from models.api import BaseEvent, LifecycleSubType, MetaEvent, MetaEventType
from models.core import EventCategory
from utils.aio import AsyncConnection, run_with_uvloop
from utils.misc import PerProcessSingletonMeta, make_exc_picklable

from .apis import BaseAccountAPI, BaseGroupAPI, BaseMessageAPI, BasePrivateAPI, BaseSupportAPI

if TYPE_CHECKING:
    from core.api_service import event_route

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
        run_with_uvloop(bot_class(bot_id, config, AsyncConnection(pipe)).start())


class BaseBotMeta(type):
    """注册所有API子类"""

    def __new__(mcs, name, *args):
        from core.bot_register import register

        cls = super().__new__(mcs, name, *args)
        if name != "BaseBot":
            cls.logger = getLogger(name)
            register(cls)
        return cls


class BaseBotSingletonMeta(BaseBotMeta, PerProcessSingletonMeta): ...


class BaseBot(BaseAccountAPI, BaseGroupAPI, BaseMessageAPI, BasePrivateAPI, BaseSupportAPI, metaclass=BaseBotMeta):
    platform: str
    transport_class: type[Transport]

    if TYPE_CHECKING:
        logger: AhaLogger

    def __init__(self, bot_id, config: dict, pipe: AsyncConnection = None):
        super().__init__()
        self.bot_id = bot_id
        self.pipe = pipe
        self.is_process_mode = pipe is not None
        self._start_server_comm = config.pop("start_server_command", None)
        self._stop_server_comm = config.pop("stop_server_command", None)
        self.config = config
        self.transport = (
            self.transport_class(self.logger, self._disconnect_cb, self._connect_cb)
            if issubclass(self.transport_class, ClientTransport)
            else self.transport_class(self.logger)
        )
        self._closing = False

    async def start(self):
        if self.is_process_mode:
            await load_locales()
            self.main_task = create_task(self._handle_requests(), eager_start=True)
        else:
            from core.api_service import event_route

            globals()["event_route"] = event_route
            self.main_task = get_running_loop().create_future()

        await load_locales(self.__class__.__module__)
        with suppress(NotImplementedError):
            await self.start_server()
        try:
            await self.transport.open(**self._get_transport_kwargs(self.config))
        except Exception as e:
            self.logger.error(_("api.service.conn.failed") % f"{e.__class__.__name__}: {e}")
            await self.close()
            return False
        self.logger.info(_("api.service.init.success"))
        create_task(self.transport.listen(self._listen_callback), eager_start=True).add_done_callback(
            lambda _: create_task(self.close(), eager_start=True)
        )

        with suppress(CancelledError):
            await self.main_task
        return True

    async def event_post(self, category, data: BaseEvent):
        if category is not EventCategory.SERVICE_REQUEST:
            data.bot_id, data.platform, data.adapter = self.bot_id, self.platform, self.__class__.__name__
        if self.is_process_mode:
            with suppress(BrokenPipeError, EOFError):
                self.pipe.send((category, data))
        else:
            await event_route(self.bot_id, category, data)

    async def _handle_requests(self):
        """仅多进程模式"""
        while True:
            try:
                call_id, method, args, kwargs = await self.pipe.recv()
            except EOFError:
                break
            try:
                self.pipe.send((EventCategory.RESPONSE, (call_id, await getattr(self, method)(call_id, *args, **kwargs))))
            except EOFError:
                pass
            except Exception as e:
                self.pipe.send((EventCategory.RESPONSE, (call_id, make_exc_picklable(e))))

    async def close(self, _=None):  # 参数为 call_id
        if not self._closing:
            self._closing = True
            await self.transport.close()
            if self.is_process_mode:
                self.pipe.close()
            else:
                # TODO: 重写这里超越界限的逻辑
                from core.api_service import clean_bot

                await clean_bot(self.bot_id)
            self.main_task.cancel()

    @classmethod
    def parse_retry_config(cls, config: dict[RetryConfigKey, int | float | list[dict[RetryConfigKey, Any] | Any]]):
        """解析重试策略配置，返回包含wait和stop实例的字典"""

        stop_types = {c.__name__: c for c in stop_base.__subclasses__()}
        wait_types = {c.__name__: c for c in wait_base.__subclasses__()}

        # 分离stop和wait配置
        stop_configs = {}
        wait_configs = {}
        for k, v in config.items():
            if k.startswith("stop_"):
                stop_configs[k] = v
            elif k.startswith("wait_"):
                wait_configs[k] = v
            else:
                cls.logger.warning(_("api.service.retry_config_422") % k)

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
                result["stop"] = stop_cls(*[cls.parse_retry_config(sub_config)["stop"] for sub_config in stop_value])
            else:
                result["stop"] = stop_cls(**stop_value)

        # 处理wait
        for wait_key, wait_value in wait_configs.items():
            wait_cls = wait_types[wait_key]

            if wait_key in ("wait_chain", "wait_combine"):
                # 递归
                result["wait"] = wait_cls(*[cls.parse_retry_config(sub_config)["wait"] for sub_config in wait_value])
            else:
                result["wait"] = wait_cls(**wait_value)

        return result

    async def _disconnect_cb(self):
        await self.event_post(
            EventCategory.META, MetaEvent(event_type=MetaEventType.LIFECYCLE, sub_type=LifecycleSubType.DISCONNECT)
        )

    async def _connect_cb(self):
        pass

    @classmethod
    @abstractmethod
    def _get_transport_kwargs(cls, config) -> dict:
        """返回用于传递给 `transport.open` 的 kwargs"""
        raise NotImplementedError

    if TYPE_CHECKING:

        @overload
        async def _listen_callback(self, data): ...

        @overload
        def _listen_callback(self, data): ...

    @abstractmethod
    def _listen_callback(self, data):
        """处理上报事件与API返回值"""
        raise NotImplementedError
