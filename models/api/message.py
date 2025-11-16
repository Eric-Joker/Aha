from enum import auto

from pydantic import Field

from ..base import BaseModelConfig, PureNameEnum


class MusicPlatform(str, PureNameEnum):
    CUSTOM = auto()
    QQ = "qq"
    NET163 = "163"


class AudioFormat(str, PureNameEnum):
    MP3 = "mp3"
    AMR = "amr"
    WMA = "wma"
    M4A = "m4a"
    OGG = "ogg"
    WAV = "wav"
    FLAC = "flac"
    SPX = "spx"


class EmojiLike(BaseModelConfig):
    tiny_id: str = Field(validation_alias="tinyId")
    nickname: str = Field(validation_alias="nickName")
    head_url: str = Field(validation_alias="headUrl")
