from pydantic import Field

from ..base import FrozenBaseModel
from .events import Message


class Reactions(FrozenBaseModel):
    emoji_id: str
    count: int


class RetrievedMessage(Message):
    reactions: list[Reactions] | None = None


class ReactionUser(FrozenBaseModel):
    user_id: str = Field(validation_alias="tinyId")
    nickname: str = Field(validation_alias="nickName")
    avatar_url: str = Field(validation_alias="avatarUrl")
