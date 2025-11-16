import os
from base64 import b64decode
from time import time
from typing import TYPE_CHECKING

from models.api import AudioFormat, RetrievedMessage
from models.exc import APIException
from models.msg import Downloadable, File, Record, Sticker

from ...apis import BaseMessageAPI
from ..utils import Utils

if TYPE_CHECKING:
    from .. import NapCat


class MessageAPI(Utils, BaseMessageAPI):
    async def send_platform_music(self: NapCat, call_id, *, user_id=None, group_id=None, platform, id):
        if group_id:
            return await self.send_group_platform_music(call_id, group_id, platform, id)
        if user_id:
            return await self.send_private_platform_music(call_id, user_id, platform, id)

    async def send_forward_msg(self: NapCat, call_id, *, user_id=None, group_id=None, forward):
        if group_id:
            return await self.send_group_forward_msg(call_id, group_id, forward)
        if user_id:
            return await self.send_private_forward_msg(call_id, user_id, forward)

    # region 消息获取
    async def get_msg(self: NapCat, call_id, message_id):
        return RetrievedMessage.model_validate(
            await self._msg_event_processor(await self._call_api(call_id, "get_msg", {"message_id": message_id}))
        )

    async def get_forward_msg(self: NapCat, call_id, message_id, raw_list=False):
        if raw := await self._call_api(call_id, "get_forward_msg", {"message_id": message_id}):
            return raw["messages"] if raw_list else await self.content2forward(message_id, raw["messages"])

    async def get_file_src(self, call_id, msg_seg: Downloadable, record_format=AudioFormat.MP3):
        if isinstance(msg_seg, Sticker):
            if isinstance(msg_seg.file, str) and msg_seg.file.startswith("https://gxh.vip.qq.com/club/item/parcel/item/"):
                return msg_seg.file
            raise APIException("无法获取该消息段实例的文件源。")
        if isinstance(msg_seg, Record):
            data = await self._call_api(call_id, "get_record", {"file_id": msg_seg.file_id, "out_format": record_format})
            return data["file"] if self.transport.local_srv else b64decode(data["base64"])
        if (data := await self._call_api(call_id, "get_file", {"file_id": msg_seg.file_id})).pop("base64", None):
            self.logger.warning(
                "不要启用 NapCat 的 enableLocalFile2Url（启用本地文件到 URL）配置，这会成倍地降低性能和增加流量。"
            )
        return data["file" if self.transport.local_srv else "url"]

    async def get_file(self, call_id, file_id):
        result: dict = await self._call_api(call_id, "get_file", {"file_id": file_id})
        if result.pop("base64", None):
            self.logger.warning(
                "不要启用 NapCat 的 enableLocalFile2Url（启用本地文件到 URL）配置，这会成倍地降低性能和增加流量。"
            )
        result["name"] = os.path.basename(result.pop("file_name"))
        if self.transport.local_srv:
            del result["url"]
        else:
            result["file"] = result.pop("url")
        return File.model_validate(result)

    async def get_reaction_users(self, call_id, message_id, emoji_id):
        raise NotImplementedError("NapCat 的 fetch_emoji_like 参数有点诡异，暂不支持。")
        return [
            EmojiLike.model_validate(item)
            for item in (
                await self._call_api(
                    call_id, "fetch_emoji_like", {"message_id": message_id, "emoji_id": emoji_id}
                )
            )["emojiLikesList"]
        ]

    # endregion
    async def set_reaction(self, call_id, message_id, emoji_id, set=True):
        return await self._call_api(
            call_id, "set_msg_emoji_like", {"message_id": message_id, "emoji_id": int(emoji_id), "set": set}
        )

    async def delete_msg(self: NapCat, call_id, message_id):
        msg = await self.get_msg(self.gen_id(), message_id)
        self_id = (await self.get_login_info(self.gen_id())).user_id
        if not (
            (await self.get_group_members(call_id, msg.group_id)).is_manager_of(self_id, msg.user_id)
            if msg.group_id
            else False
        ):
            if msg.user_id != self_id:
                raise APIException("无权撤回该消息。")
            if msg.time <= time() - 120:
                raise APIException("消息已超过2分钟，无法撤回。")

        return await self._call_api(call_id, "delete_msg", {"message_id": message_id})

    async def set_input_status(self, call_id, status):
        return await self._call_api(call_id, "set_input_status", {"status": status})
