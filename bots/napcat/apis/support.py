
from typing import Literal

from models.api import AICharacterList, APIVersion

from ...apis import BaseSupportAPI


class SupportAPI(BaseSupportAPI):
    # region AI 声聊
    async def get_ai_characters(self, call_id, group_id: str | int, chat_type: Literal[1, 2]):
        return AICharacterList(
            item["characters"]
            for item in await self._call_api(call_id, "get_ai_characters", {"group_id": group_id, "chat_type": chat_type})
        )

    async def get_ai_record(self, call_id, group_id: str | int, character_id: str, text: str):
        return await self._call_api(call_id, "get_ai_record", {"group_id": group_id, "character": character_id, "text": text})

    # endregion

    # region 状态检查
    async def can_send_image(self, call_id):
        return (await self._call_api(call_id, "can_send_image"))["yes"]

    async def can_send_record(self, call_id, group_id: str | int):
        return (await self._call_api(call_id, "can_send_record", {"group_id": group_id}))["yes"]

    # endregion

    # region OCR（仅 windows 可用）
    async def ocr_image(self, call_id, image):
        return await self._call_api(
            call_id,
            "ocr_image",
            {"image": await self.prepare_file(image if isinstance(image, str) else image.file, self.transport.local_srv)},
        )

    # endregion

    # region 其它
    async def get_version_info(self, call_id):
        return APIVersion.model_validate(await self._call_api(call_id, "get_version_info"))

    async def stop_server(self, call_id):
        # TODO: 测试
        return await self._call_api(call_id, "bot_exit")

    # endregion

    # region 实验性功能
    pass
    # endregion
