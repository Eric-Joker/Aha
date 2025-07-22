# Copyright (C) 2025 github.com/Eric-Joker
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
import binascii
import os
import sys
from base64 import b64decode
from logging import getLogger
from multiprocessing import Queue

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from uvicorn import run

logger = getLogger(__name__)


def load_public_key(public_key_path: str) -> Ed25519PublicKey:
    if not os.path.exists(public_key_path):
        logger.warning(f"Public key file not found at {public_key_path}")
        return None

    try:
        with open(public_key_path, "rb") as f:
            public_key_data = f.read()
        public_key = serialization.load_pem_public_key(public_key_data)
        if not isinstance(public_key, Ed25519PublicKey):
            logger.error("The provided key is not an Ed25519 public key")
            return None
        return public_key
    except Exception as e:
        logger.error(f"Failed to load public key: {str(e)}")
        return None


class SignatureVerificationMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 跳过验证
        if getattr((request := Request(scope, receive)).scope.get("endpoint"), "_skip_signature_verify", False):
            await self.app(scope, receive, send)
            return

        # 公钥不存在
        if public_key is None:
            if "signature" in request.headers:
                await JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={"detail": "Server is not configured with public key"},
                )(scope, receive, send)
                return

            # 无签名头时允许所有请求
            await self.app(scope, receive, send)
            return

        if request.method not in ("GET", "HEAD"):
            if not (signature_header := request.headers.get("signature")):
                await JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": "Missing signature header"})(
                    scope, receive, send
                )
                return

            try:
                signature_bytes = b64decode(signature_header)
            except binascii.Error as e:
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

            try:
                public_key.verify(signature_bytes, body := await request.body())
            except InvalidSignature:
                await JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": "Invalid signature"})(
                    scope, receive, send
                )
                return
            except Exception as e:
                await JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(e)})(scope, receive, send)
                return

            # 重置请求体
            async def receive_body() -> Message:
                return {"type": "http.request", "body": body, "more_body": False}

            receive = receive_body

        await self.app(scope, receive, send)


app = FastAPI()
app.add_middleware(SignatureVerificationMiddleware)

task_queue: Queue = None
public_key: Ed25519PublicKey = None


def run_fastapi(port, queue):
    global task_queue, public_key
    task_queue = queue
    public_key = load_public_key(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "ed25519.pem"))
    if public_key is None:
        logger.warning("Running without signature verification! This is insecure for non-GET/HEAD requests.")

    import fastapi_modules
    from cores import install_uvloop

    install_uvloop()
    run(app, host="0.0.0.0", port=port)
