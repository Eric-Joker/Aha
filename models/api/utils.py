from ..base import PureNameEnum


class Sex(str, PureNameEnum):
    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"


class Role(str, PureNameEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class AudioFormat(str, PureNameEnum):
    MP3 = "mp3"
    AMR = "amr"
    WMA = "wma"
    M4A = "m4a"
    OGG = "ogg"
    WAV = "wav"
    FLAC = "flac"
    SPX = "spx"
