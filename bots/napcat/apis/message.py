
from models.api import AudioFormat, EmojiLike, Message
from models.msg import Image, Record
from utils.misc import check_single_true

from ...apis import BaseMessageAPI


class MessageAPI(BaseMessageAPI):
    # region 消息发送
    async def send_msg(self, call_id, *, user_id=None, group_id=None, msg=None, at=None, reply=None, image=None):
        if group_id:
            return await self.send_group_msg(call_id, group_id, msg, at, reply, image)
        if user_id:
            return await self.send_private_msg(call_id, user_id, msg, at, reply, image)

    async def send_unescape_text(self, call_id, *, user_id=None, group_id=None, text):
        if group_id:
            return await self.send_group_unescape_text(call_id, group_id, text)
        if user_id:
            return await self.send_private_unescape_text(call_id, user_id, text)

    async def send_image(self, call_id, *, user_id=None, group_id=None, image):
        if group_id:
            return await self.send_group_image(call_id, group_id, image)
        if user_id:
            return await self.send_private_image(call_id, user_id, image)

    async def send_record(self, call_id, *, user_id=None, group_id=None, file):
        if group_id:
            return await self.send_group_record(call_id, group_id, file)
        if user_id:
            return await self.send_private_record(call_id, user_id, file)

    async def send_dice(self, call_id, *, user_id=None, group_id=None, value=1):
        if group_id:
            return await self.send_group_dice(call_id, group_id, value)
        if user_id:
            return await self.send_private_dice(call_id, user_id, value)

    async def send_rps(self, call_id, *, user_id=None, group_id=None, value=1):
        if group_id:
            return await self.send_group_rps(call_id, group_id, value)
        if user_id:
            return await self.send_private_rps(call_id, user_id, value)

    async def send_file(self, call_id, *, user_id=None, group_id=None, file, name=None):
        if group_id:
            return await self.send_group_file(call_id, group_id, file, name)
        if user_id:
            return await self.send_private_file(call_id, user_id, file, name)

    async def send_music(self, call_id, *, user_id=None, group_id=None, platform, id):
        if group_id:
            return await self.send_group_music(call_id, group_id, platform, id)
        if user_id:
            return await self.send_private_music(call_id, user_id, platform, id)

    async def send_custom_music(
        self, call_id, *, user_id=None, group_id=None, url, image=None, audio=None, title=None, content=None
    ):
        if group_id:
            return await self.send_group_custom_music(call_id, group_id, url, title, content, image)
        if user_id:
            return await self.send_private_custom_music(call_id, user_id, url, title, content, image)

    async def send_forward_msg(self, call_id, *, user_id=None, group_id=None, forward):
        if group_id:
            return await self.send_group_forward_msg(call_id, group_id, forward)
        if user_id:
            return await self.send_private_forward_msg(call_id, user_id, forward)

    async def send_forward_msg_by_id(self, call_id, *, user_id=None, group_id=None, messages):
        if group_id:
            return await self.send_group_forward_msg_by_id(call_id, group_id, messages)
        if user_id:
            return await self.send_private_forward_msg_by_id(call_id, user_id, messages)

    async def poke(self, call_id, *, user_id, group_id=None):
        if group_id:
            return await self.group_poke(call_id, group_id, user_id)
        return await self.friend_poke(call_id, user_id)

    async def set_msg_emoji_like(self, call_id, message_id, emoji_id, set=True):
        return await self._call_api(
            call_id, "set_msg_emoji_like", {"message_id": message_id, "emoji_id": int(emoji_id), "set": set}
        )

    # endregion

    # region 消息获取
    async def get_group_msg_history(self, call_id, group_id, message_seq, number=20, reverseOrder=False):
        return [
            Message.model_validate(self._msg_event_processor(data["message"]))
            for data in await self._call_api(
                call_id,
                "get_group_msg_history",
                {"group_id": group_id, "message_seq": message_seq, "number": number, "reverseOrder": reverseOrder},
            )
        ]

    async def get_msg(self, call_id, message_id):
        return Message.model_validate(self._msg_event_processor(await self._call_api(call_id, "get_msg", {"message_id": message_id})))

    async def get_forward_msg(self, call_id, message_id):
        return self.content2forward(
            message_id, (await self._call_api(call_id, "get_forward_msg", {"message_id": message_id}))["messages"]
        )

    async def get_friend_msg_history(self, call_id, user_id, message_seq, number=20, reverseOrder=False):
        return [
            Message.model_validate(data)
            for data in await self._call_api(
                call_id,
                "get_friend_msg_history",
                {"user_id": user_id, "message_seq": message_seq, "number": number, "reverseOrder": reverseOrder},
            )
        ]

    async def get_record(self, call_id, file=None, file_id=None, out_format: AudioFormat = AudioFormat.MP3):
        check_single_true(file=file, file_id=file_id)
        return Record.model_validate(
            await self._call_api(call_id, "get_record", {"file": file, "file_id": file_id, "out_format": out_format})
        )

    async def get_image(self, call_id, file=None, file_id=None):
        check_single_true(file=file, file_id=file_id)
        return Image.model_validate(await self._call_api(call_id, "get_image", {"file": file, "file_id": file_id}))

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

    async def delete_msg(self, call_id, message_id):
        # TODO: 获取删除消息的结果
        return await self._call_api(call_id, "delete_msg", {"message_id": message_id})

    async def set_input_status(self, call_id, status):
        return await self._call_api(call_id, "set_input_status", {"status": status})

    pass
