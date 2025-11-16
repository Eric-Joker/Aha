from collections.abc import Callable
from contextlib import suppress
from logging import getLogger
from typing import TYPE_CHECKING

from aiofiles import open
from anyio import Path

from core.deduplicator import NoneDeduplicator
from core.i18n import _
from core.transports import ServerTransport
from models.api import LifecycleSubType, MetaEvent, MetaEventType
from models.core import EventCategory

from ..base import BaseBot

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from fastapi import FastAPI as fastapi_FastAPI
    from starlette.types import ASGIApp, Receive, Scope, Send
    from uvicorn import Server

__all__ = ("app", "FastAPI", "skip_signature_verify")

app: fastapi_FastAPI = None


def skip_signature_verify(wrapped: Callable = None):
    if wrapped is None:
        return skip_signature_verify
    wrapped._skip_signature_verify = True
    return wrapped


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


class SignatureVerificationMiddleware:
    __slots__ = ("app",)

    public_key: Ed25519PublicKey = None

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        from fastapi import Request, status

        # 跳过验证
        if getattr((request := Request(scope, receive)).scope.get("endpoint"), "_skip_signature_verify", False):
            await self.app(scope, receive, send)
            return

        from fastapi.responses import JSONResponse

        # 公钥不存在
        if self.public_key is None:
            if "signature" in request.headers:
                await JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={"detail": "Server is not configured with public key"},
                )(scope, receive, send)
                return

            # 无签名头时允许所有请求
            await self.app(scope, receive, send)
            return

        if not (signature_header := request.headers.get("signature")):
            await JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": "Missing signature header"})(
                scope, receive, send
            )
            return

        from base64 import b64decode
        from binascii import Error

        try:
            signature_bytes = b64decode(signature_header)
        except Error as e:
            await JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": f"Invalid base64 encoding in signature header: {str(e)}"},
            )(scope, receive, send)
            return
        except Exception as e:
            await JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST, content={"detail": f"Error decoding signature: {str(e)}"}
            )(scope, receive, send)
            return

        from cryptography.exceptions import InvalidSignature

        try:
            self.public_key.verify(signature_bytes, body := await request.body())
        except InvalidSignature:
            await JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": "Invalid signature"})(
                scope, receive, send
            )
            return
        except Exception as e:
            await JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(e)})(scope, receive, send)
            return

        async def receive_body():
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, receive_body, send)


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
        SignatureVerificationMiddleware.public_key = await load_public_key(config.pop("public_key", await Path.cwd() / "ed25519.pem"))
        if SignatureVerificationMiddleware.public_key is None:
            self.logger.warning(_("fastapi.secrets.warn"))

        app.add_middleware(SignatureVerificationMiddleware)
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
    deduplicator = NoneDeduplicator

    @property
    def _transport_kwargs(self):
        return {"config": self.config}

    @classmethod
    async def post(cls, key, data=None, lang=None):
        await cls().pipe.send((EventCategory.EXTERNAL, (key, data, lang)))
