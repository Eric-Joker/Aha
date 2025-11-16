
from asyncio import TimeoutError, create_subprocess_shell, subprocess, wait_for
from contextlib import suppress
from typing import Literal

from models.api import AICharacterList, APIVersion
from models.msg import File, Image

from .base import BaseAPI


class BaseSupportAPI(BaseAPI):
    # region AI 声聊
    async def get_ai_characters(self, call_id, group_id: str | int, chat_type: Literal[1, 2]) -> AICharacterList:
        raise NotImplementedError

    async def get_ai_record(self, call_id, group_id: str | int, character_id: str, text: str) -> str:
        """
        发送 AI 声聊并返回链接 str（似乎用不了）
        :param group_id: 群号
        :param character_id: 角色ID
        :param text: 文本
        :return: 链接
        """
        raise NotImplementedError

    # endregion

    # region 状态检查
    async def can_send_image(self, call_id) -> bool:
        raise NotImplementedError

    async def can_send_record(self, call_id, group_id: str | int) -> bool:
        raise NotImplementedError

    # endregion

    # region OCR
    async def ocr_image(self, call_id, image: str | Image | File) -> list[dict]:
        raise NotImplementedError

    # endregion

    # region 其它
    async def get_version_info(self, call_id) -> APIVersion:
        raise NotImplementedError

    async def start_server(self, _):
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

    async def stop_server(self, call_id):
        return

    async def restart_server(self, call_id):
        return (await self.start_server(call_id), await self.stop_server(call_id))

    # endregion

    # region 实验性功能
    pass
    # endregion
