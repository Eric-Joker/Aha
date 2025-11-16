from typing import TYPE_CHECKING, Literal

from models.api import APIVersion
from models.api.events import HeartbeatStatus
from models.msg import File, Image

if TYPE_CHECKING:
    from bots.napcat import AICharacterList


class SupportAPI:
    # region AI 声聊
    @staticmethod
    async def get_ai_characters(group_id: str, chat_type: Literal[1, 2], *, bot: int = None) -> AICharacterList:
        pass

    @staticmethod
    async def get_ai_record(group_id: str, character_id: str, text: str, *, bot: int = None) -> str:
        """
        发送 AI 声聊并返回链接 str（似乎用不了）
        :param group_id: 群号
        :param character_id: 角色ID
        :param text: 文本
        :return: 链接
        """

    # endregion

    # region 状态检查
    @staticmethod
    async def can_send_image(*, bot: int = None) -> bool:
        pass

    @staticmethod
    async def can_send_record(group_id: str, *, bot: int = None) -> bool:
        pass

    # endregion

    # region OCR
    @staticmethod
    async def ocr_image(image: str | Image | File, *, bot: int = None) -> list[dict]:
        pass

    # endregion

    # region 其它
    @staticmethod
    async def get_version_info(*, bot: int = None) -> APIVersion:
        pass

    @staticmethod
    async def start_server(*, bot: int = None):
        pass

    @staticmethod
    async def stop_server(*, bot: int = None):
        pass

    @staticmethod
    async def restart_server(*, bot: int = None):
        pass

    @staticmethod
    async def get_status(*, bot: int = None) -> HeartbeatStatus:
        pass

    # endregion

    # region 实验性功能
    pass
    # endregion
