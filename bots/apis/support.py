from asyncio import TimeoutError, create_subprocess_shell, subprocess, wait_for
from contextlib import suppress
from typing import TYPE_CHECKING

from models.api import APIVersion
from models.api.events import HeartbeatStatus

from .base import BaseAPI

if TYPE_CHECKING:
    from .. import BaseBot


class BaseSupportAPI(BaseAPI):
    async def get_version_info(self, call_id) -> APIVersion:
        raise NotImplementedError

    async def start_server(self: BaseBot, _):
        if self._start_server_comm:
            proc = await create_subprocess_shell(self._start_server_comm, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                await wait_for(proc.communicate(), timeout=300)
                return proc.returncode
            except TimeoutError:
                with suppress(Exception):
                    proc.kill()
                return -1
        raise NotImplementedError

    async def stop_server(self, call_id) -> None:
        raise NotImplementedError

    async def restart_server(self: BaseBot, call_id) -> None:
        if self._start_server_comm:
            return await self.stop_server(call_id), await self.start_server(call_id), 
        raise NotImplementedError

    async def get_status(self, call_id) -> HeartbeatStatus:
        raise NotImplementedError
