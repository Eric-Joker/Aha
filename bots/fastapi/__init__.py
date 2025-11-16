from asyncio import Future, Lock, get_running_loop, wait_for
from base64 import b64decode
from binascii import Error
from collections.abc import Callable
from contextlib import suppress
from logging import getLogger
from time import time
from typing import TYPE_CHECKING

from aiofiles import open
from anyio import Path

from core.i18n import _
from core.transports import ServerTransport
from models.api import External, LifecycleSubType, MetaEvent, MetaEventType
from models.core import EventCategory

from ..base import BaseBot

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from fastapi import FastAPI as fastapi_FastAPI
    from starlette.types import Scope
    from uvicorn import Server

__all__ = ("app", "FastAPI", "skip_verify")

app: fastapi_FastAPI = None


def skip_verify(wrapped: Callable = None):
    if wrapped is None:
        return skip_verify
    from fastapi.routing import APIRoute, APIWebSocketRoute

    for r in app.routes:
        if (r.__class__ is APIRoute or r.__class__ is APIWebSocketRoute) and r.endpoint is wrapped:
            VerificationMiddleware.pass_paths.add(r.path)
            return wrapped

    assert False


async def load_public_key(public_key_path: Path) -> Ed25519PublicKey | None:
    if not await public_key_path.exists():
        getLogger("AHA (FastAPI)").warning(_("fastapi.secrets.404") % str(public_key_path))
        return None

    try:
        async with open(public_key_path, "rb") as f:
            public_key_data = await f.read()
        from cryptography.hazmat.primitives import serialization

        public_key: Ed25519PublicKey = serialization.load_pem_public_key(public_key_data)
        """if not isinstance(public_key, Ed25519PublicKey):
            getLogger("AHA (FastAPI)").error("The provided key is not an Ed25519 public key")
            return None"""
        return public_key
    except Exception as e:
        getLogger("AHA (FastAPI)").error(_("fastapi.secrets.invalid") % e)
        return None


class VerificationMiddleware:
    __slots__ = ("app", "_nonce_cache", "_cache_lock")

    public_key: Ed25519PublicKey = None
    pass_paths = set()

    DELTA = 300

    def __init__(self, app):
        self.app = app
        self._nonce_cache = {}
        self._cache_lock = Lock()

    async def __call__(self, scope: Scope, receive, send):
        from fastapi import status
        from fastapi.responses import JSONResponse, Response

        is_http = scope.get("type") == "http"

        async def reject(code=status.HTTP_401_UNAUTHORIZED, content=None, res_cls=Response):
            if is_http:
                await res_cls(content, code)(scope, receive, send)
            else:
                await send({"type": "websocket.close", "code": 1008})

        # 跳过验证
        if scope.get("path") in self.pass_paths or scope.get("type") == "lifespan":
            await self.app(scope, receive, send)
            return

        # 提取请求头
        timestamp = nonce = signature = None
        for name, value in scope.get("headers"):
            if not timestamp and name == b"timestamp":
                timestamp = value
            elif not nonce and name == b"nonce":
                nonce = value
            elif not signature and name == b"signature":
                signature = value

        # 公钥不存在
        if self.public_key is None:
            if signature:
                return await reject(
                    status.HTTP_503_SERVICE_UNAVAILABLE, {"detail": "Server is not configured with public key"}, JSONResponse
                )
            await self.app(scope, receive, send)
            return

        # 验证请求头
        if not signature or len(signature) > 88 or not nonce or len(nonce) > 24 or not timestamp or len(timestamp) > 12:
            return await reject()

        try:
            b64decode(nonce := nonce.decode(), validate=True)
            i_timestamp = int.from_bytes(b64decode(timestamp := timestamp.decode(), validate=True))
            b_signature = b64decode(signature := signature.decode(), validate=True)
        except Error:
            return await reject()

        # 防重放
        now = time()
        if i_timestamp > now - self.DELTA and i_timestamp < now + self.DELTA:
            async with self._cache_lock:
                # 清理过期项。避免迭代时修改
                for k in [k for k, exp in self._nonce_cache.items() if exp <= now]:
                    del self._nonce_cache[k]
                if nonce in self._nonce_cache:
                    return await reject()
        else:
            return await reject()

        # 验证签名
        try:
            self.public_key.verify(b_signature, f"{timestamp}|{nonce}".encode())
        except Exception:
            return await reject()

        # 记录 nonce
        async with self._cache_lock:
            self._nonce_cache[nonce] = i_timestamp + self.DELTA

        await self.app(scope, receive, send)


class FastAPIConnection(ServerTransport):
    __slots__ = ("logger", "server")

    def __init__(self, _=None):
        self.logger = getLogger("AHA (FastAPI)")
        self.server: Server

    async def open(self, config: dict):
        global app
        # FastAPI
        from fastapi import FastAPI as fastapi_FastAPI

        app = fastapi_FastAPI()
        VerificationMiddleware.public_key = await load_public_key(config.pop("public_key", await Path.cwd() / "ed25519.pem"))
        if VerificationMiddleware.public_key is None:
            self.logger.warning(_("fastapi.secrets.warn"))

        app.add_middleware(VerificationMiddleware)
        from fastapi_modules import init_load_mod

        # modules
        await init_load_mod()

        # Uvicorn
        import uvicorn.lifespan.on
        from uvicorn import Config, Server

        _original_startup = uvicorn.lifespan.on.LifespanOn.startup

        async def startup(self, *args, **kwargs):
            await _original_startup(self, *args, **kwargs)
            await FastAPI().event_post(
                EventCategory.META, MetaEvent(meta_event_type=MetaEventType.LIFECYCLE, sub_type=LifecycleSubType.CONNECT)
            )

        uvicorn.lifespan.on.LifespanOn.startup = startup

        log_cfg = {
            "version": 1,
            "disable_existing_loggers": False,
            "incremental": True,
            "formatters": {},
            "handlers": {},
            "loggers": {
                "uvicorn": {"level": "INFO"},
                "uvicorn.error": {"level": "INFO"},
                "uvicorn.access": {"level": "INFO"},
            },
        }
        drops = {"self", "cls"}
        args = [n for n in config if n not in drops]
        self.server = Server(Config(app, log_config=log_cfg, **{k: v for k, v in config.items() if k in args}))

    async def listen(self, _):
        with suppress(SystemExit):
            await self.server._serve()

    async def close(self):
        with suppress(AttributeError):
            await self.server.shutdown()


class FastAPI(BaseBot):
    platform = "Web"
    transport_class = FastAPIConnection
    _calls: dict[str, Future] = None

    @property
    def _transport_kwargs(self):
        return {"config": self.config}

    def __init__(self, *args, **kwargs):
        FastAPI._calls = {}
        super().__init__(*args, **kwargs)

    @classmethod
    async def post(cls, key, data=None, lang=None):
        await cls().event_post(EventCategory.EXTERNAL, External(key=key, data=data, lang=lang))

    @classmethod
    async def get(cls, key, data=None, lang=None, timeout=64800):
        cls._calls[key] = future = get_running_loop().create_future()
        await cls.post(key, data, lang)
        return await wait_for(future, timeout)

    async def set_result(self, _, key, data):
        self._calls[key].set_result(data)

    async def send_msg(self, _, *, user_id, msg, **__):
        await self.set_result(user_id, msg)
