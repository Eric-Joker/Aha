from enum import Enum, auto

from pydantic import Field

from models.api import LastestMsgs as AhaLastestMsgs


class StickerType(Enum):
    QQFACE = auto()
    MARKETFACE = auto()
    POKE = auto()
    DICE = auto()
    RPS = auto()


class LastestMsgs(AhaLastestMsgs):
    peer_uin: str = Field(validation_alias="peerUin")
    send_nick_name: str = Field(validation_alias="sendNickName")
    send_member_name: str = Field(validation_alias="sendMemberName")
    msg_id: str = Field(validation_alias="msgId")
    chat_type_num: int = Field(validation_alias="chatType")
    msg_time_str: str = Field(validation_alias="msgTime")


MUSIC_PLATFORM_MAP = {  # TODO: 补齐
    "163": "163",  # 不知道
    "QQ音乐": "qq",
    "kugou": "kugou",  # 不知道
    "migu": "migu",  # 不知道
    "kuwo": "kuwo",  # 不知道
}
