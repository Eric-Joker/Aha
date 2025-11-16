
import signal
import sys
from asyncio import create_task, get_running_loop, run, sleep
from contextlib import suppress
from logging import getLogger
from typing import Any, ClassVar, overload

from core.deduplicator import Deduplicator
from core.i18n import _, load_locales
from core.log import AhaLogger, setup_logging
from core.transports import Transport
from models.core import EventCategory
from models.metas import PerProcessSingletonMeta
from utils.aio import AsyncConnection, install_uvloop
from utils.typekit import make_exception_pickleable

from .apis import BaseAccountAPI, BaseGroupAPI, BaseMessageAPI, BasePrivateAPI, BaseSupportAPI

status = {}


def api_worker(bot_class: type[BaseBot], bot_id, pipe, config, base64_buffer, lang, log):
    install_uvloop()
    setup_logging(log)
    status["base64_buffer"] = base64_buffer
    status["def_lang"] = lang

    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if sys.platform == "win32":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)

    with suppress(KeyboardInterrupt):
        run(bot_class(bot_id, config, AsyncConnection(pipe)).start())


class BaseBotMeta(PerProcessSingletonMeta):
    """注册所有API子类"""

    def __init__(cls, name, bases, attrs):
        from core.bot_register import register

        super().__init__(name, bases, attrs)
        register(cls)


class BaseBot(BaseAccountAPI, BaseGroupAPI, BaseMessageAPI, BasePrivateAPI, BaseSupportAPI, metaclass=BaseBotMeta):
    platform: str
    transport_class: ClassVar[type[Transport]]
    deduplicator: ClassVar[type[Deduplicator]]

    @property
    def _transport_kwargs(self) -> dict:
        """返回用于传递给 `transport.connect` 的 kwargs"""
        raise NotImplementedError

    def __init__(self, bot_id, config: dict, pipe: AsyncConnection = None):
        self.bot_id = bot_id
        self.pipe = pipe
        self.is_processing_mode = pipe is not None
        self.logger: AhaLogger = getLogger(self.__class__.__name__)
        self._start_server_comm = config.pop("start_server_command", None)
        self.config = config
        self.transport: Transport = self.transport_class(self.logger)

    async def start(self):
        if self.is_processing_mode:
            await load_locales(self.__class__.__module__)
            self._request_listen = create_task(self._handle_requests())

        try:
            await self.transport.open(**self._transport_kwargs)
        except Exception as e:
            self.logger.error(_("api.service.conn.failed") % e)
            await self.close()
            return False
        self.logger.info(_("api.service.init.success"))
        create_task(self.transport.listen(self._listen_callback))

        if self.is_processing_mode:
            await get_running_loop().create_future()
        return True

    async def event_post(self, catrgory, data):
        if self.is_processing_mode:
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
                await self.event_post(EventCategory.RESPONSE, (call_id, await getattr(self, method)(call_id, *args, **kwargs)))
            except BaseException as e:
                create_task(self.event_post(EventCategory.RESPONSE, (call_id, make_exception_pickleable(e))))
            await sleep(0.001)

    async def close(self, _=None):  # 参数为 call_id
        await self.transport.close()
        if self.is_processing_mode:
            self._request_listen.cancel()
            self.pipe.close()
        else:
            # TODO: 重写这里超越界限的逻辑
            from core.api_service import bots

            bots[self.bot_id].server_ok.set()  # 让启动流程通过

    @overload
    async def _listen_callback(self, data): ...

    @overload
    def _listen_callback(self, data): ...

    def _listen_callback(self, data):
        """处理上报事件与API返回值"""
        raise NotImplementedError

    async def _call_api(self, echo, action, params=None, timeout=300) -> Any:
        """调用 `self.transport.send` 并获取返回值或报错"""
        raise NotImplementedError
