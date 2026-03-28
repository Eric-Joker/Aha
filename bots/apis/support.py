from asyncio import create_subprocess_shell, subprocess
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
            await create_subprocess_shell(self._start_server_comm, subprocess.PIPE, subprocess.PIPE, subprocess.PIPE)
            return
        raise NotImplementedError

    async def stop_server(self, call_id, close_adapter=True) -> None:
        raise NotImplementedError
        await self.close()

    async def restart_server(self: BaseBot, call_id) -> None:
        if self._start_server_comm:
            return (
                await self.stop_server(call_id, False),
                await self.start_server(call_id),
            )
        raise NotImplementedError

    async def get_status(self, call_id) -> HeartbeatStatus:
        raise NotImplementedError
