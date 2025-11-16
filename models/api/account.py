import contextlib
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BeforeValidator, Field, model_validator

from models.api.utils import Sex

from ..base import FrozenBaseModel
from .events import Message


class LoginInfo(FrozenBaseModel):
    nickname: str
    user_id: Annotated[str, BeforeValidator(str)]


class Friend(FrozenBaseModel):
    user_id: Annotated[str, BeforeValidator(str)]
    nickname: str
    remark: str | None = None
    sex: str | None = None
    level: int | None = None
    age: int | None = None
    birthday: date | None = None
    phone_num: str | None = None
    email: str | None = None
    category_id: int | None = None

    @model_validator(mode="before")
    @classmethod
    def combine_birthday_fields(cls, data):
        if isinstance(data, dict):
            year = data.get("birthday_year")
            month = data.get("birthday_month")
            day = data.get("birthday_day")
            if all(isinstance(x, int) for x in (year, month, day)):
                with contextlib.suppress(ValueError):
                    data["birthday"] = date(year, month, day)
            # 移除原始的三个生日字段
            data.pop("birthday_year", None)
            data.pop("birthday_month", None)
            data.pop("birthday_day", None)

        return data


class FriendCategory(FrozenBaseModel):
    category_id: int = Field(validation_alias="categoryId")
    category_name: str = Field(validation_alias="categoryName")
    online_count: int | None = Field(None, validation_alias="onlineCount")
    friends: list[Friend]


class LastestMsgs(FrozenBaseModel):
    remark: str
    peer_name: str = Field(validation_alias="peerName")
    latest_msg: Message = Field(validation_alias="lastestMsg")
    
    @property
    def sender(self):
        return self.latest_msg.sender

    @property
    def sender_uid(self):
        return self.latest_msg.user_id
    
    @property
    def msg_time(self):
        return self.latest_msg.time
    
    @property
    def chat_type(self):
        return self.latest_msg.sub_type

    @property
    def message_id(self):
        return self.latest_msg.message_id
    
    @property
    def peer_id(self):
        return self.latest_msg.group_id or self.latest_msg.user_id


class Stranger(FrozenBaseModel):
    user_id: Annotated[str, BeforeValidator(str)]
    nickname: str
    sex: Sex
    age: int | None = None
    level: int | None = None
    bio: str | None = None
    reg_time: Annotated[datetime, BeforeValidator(datetime.fromtimestamp)] | None = None
    is_vip: bool | None = None
    remark: str | None = None


class UserStatus(FrozenBaseModel):
    status: int
    ext_status: Any = None
