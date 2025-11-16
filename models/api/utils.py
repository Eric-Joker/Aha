from ..base import PureNameEnum


class Sex(str, PureNameEnum):
    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"


class Role(str, PureNameEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class HonorType(str, PureNameEnum):
    TALKATIVE = "talkative"
    PERFORMER = "performer"
    EMOTION = "emotion"

