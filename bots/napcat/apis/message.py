import os
from base64 import b64decode
from time import time
from typing import TYPE_CHECKING

from models.api import AudioFormat, EmojiLike, Message
from models.exc import APIException
from models.msg import Downloadable, File, Record, Sticker

from ...apis import BaseMessageAPI
from ..utils import Utils

if TYPE_CHECKING:
    from .. import NapCat


class MessageAPI(Utils, BaseMessageAPI):
    # region 消息发送
    async def send_msg(self: NapCat, call_id, *, user_id=None, group_id=None, msg=None, at=None, reply=None, image=None):
        if group_id:
            return await self.send_group_msg(call_id, group_id, msg, at, reply, image)
        if user_id:
            return await self.send_private_msg(call_id, user_id, msg, at, reply, image)

    async def send_raw_msg(self: NapCat, call_id, *, user_id=None, group_id=None, data):
        if group_id:
            return await self.send_group_raw_msg(call_id, group_id, data)
        if user_id:
            return await self.send_private_raw_msg(call_id, user_id, data)

    async def send_image(self: NapCat, call_id, *, user_id=None, group_id=None, image):
        if group_id:
            return await self.send_group_image(call_id, group_id, image)
        if user_id:
            return await self.send_private_image(call_id, user_id, image)

    async def send_record(self: NapCat, call_id, *, user_id=None, group_id=None, file):
        if group_id:
            return await self.send_group_record(call_id, group_id, file)
        if user_id:
            return await self.send_private_record(call_id, user_id, file)

    async def send_dice(self: NapCat, call_id, *, user_id=None, group_id=None, value=1):
        if group_id:
            return await self.send_group_dice(call_id, group_id, value)
        if user_id:
            return await self.send_private_dice(call_id, user_id, value)

    async def send_rps(self: NapCat, call_id, *, user_id=None, group_id=None, value=1):
        if group_id:
            return await self.send_group_rps(call_id, group_id, value)
        if user_id:
            return await self.send_private_rps(call_id, user_id, value)

    async def send_file(self: NapCat, call_id, *, user_id=None, group_id=None, file, name=None):
        if group_id:
            return await self.send_group_file(call_id, group_id, file, name)
        if user_id:
            return await self.send_private_file(call_id, user_id, file, name)

    async def send_music(self: NapCat, call_id, *, user_id=None, group_id=None, platform, id):
        if group_id:
            return await self.send_group_music(call_id, group_id, platform, id)
        if user_id:
            return await self.send_private_music(call_id, user_id, platform, id)

    async def send_custom_music(
        self: NapCat, call_id, *, user_id=None, group_id=None, url, image=None, audio=None, title=None, content=None
    ):
        if group_id:
            return await self.send_group_custom_music(call_id, group_id, url, title, content, image)
        if user_id:
            return await self.send_private_custom_music(call_id, user_id, url, title, content, image)

    async def send_forward_msg(self: NapCat, call_id, *, user_id=None, group_id=None, forward):
        if group_id:
            return await self.send_group_forward_msg(call_id, group_id, forward)
        if user_id:
            return await self.send_private_forward_msg(call_id, user_id, forward)

    async def send_forward_msg_by_id(self: NapCat, call_id, *, user_id=None, group_id=None, messages):
        if group_id:
            return await self.send_group_forward_msg_by_id(call_id, group_id, messages)
        if user_id:
            return await self.send_private_forward_msg_by_id(call_id, user_id, messages)

    async def poke(self: NapCat, call_id, *, user_id, group_id=None):
        if group_id:
            return await self.group_poke(call_id, group_id, user_id)
        return await self.friend_poke(call_id, user_id)

    async def set_msg_emoji_like(self, call_id, message_id, emoji_id, set=True):
        return await self._call_api(
            call_id, "set_msg_emoji_like", {"message_id": message_id, "emoji_id": int(emoji_id), "set": set}
        )

    # endregion

    # region 消息获取
    async def get_group_msg_history(self: NapCat, call_id, group_id, message_seq, number=20, reverseOrder=False):
        return [
            Message.model_validate(await self._msg_event_processor(data["message"]))
            for data in await self._call_api(
                call_id,
                "get_group_msg_history",
                {"group_id": group_id, "message_seq": message_seq, "number": number, "reverseOrder": reverseOrder},
            )
        ]

    async def get_msg(self: NapCat, call_id, message_id):
        return Message.model_validate(
            await self._msg_event_processor(await self._call_api(call_id, "get_msg", {"message_id": message_id}))
        )

    async def get_forward_msg(self: NapCat, call_id, message_id, raw_list=False):
        if raw := await self._call_api(call_id, "get_forward_msg", {"message_id": message_id}):
            return raw["messages"] if raw_list else await self.content2forward(message_id, raw["messages"])

    async def get_friend_msg_history(self, call_id, user_id, message_seq, number=20, reverseOrder=False):
        return [
            Message.model_validate(data)
            for data in await self._call_api(
                call_id,
                "get_friend_msg_history",
                {"user_id": user_id, "message_seq": message_seq, "number": number, "reverseOrder": reverseOrder},
            )
        ]

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

    async def fetch_emoji_like(self, call_id, message_id, emoji_id, emoji_type):
        return [
            EmojiLike.model_validate(item)
            for item in (
                await self._call_api(
                    call_id, "fetch_emoji_like", {"message_id": message_id, "emoji_id": emoji_id, "emoji_type": emoji_type}
                )
            )["emojiLikesList"]
        ]

    # endregion
    async def delete_msg(self: NapCat, call_id, message_id):
        msg = await self.get_msg(self.gen_id(), message_id)
        self_id = (await self.get_login_info(self.gen_id())).user_id
        if not (
            (await self.get_group_member_list(call_id, msg.group_id)).is_manager_of(self_id, msg.user_id)
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
