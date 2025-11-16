from collections.abc import Mapping
from enum import Enum, auto
from typing import Any

from attrs import define


# region ipc
class EventCategory(Enum):
    SERVICE_REQUEST = auto()
    RESPONSE = "api_response"
    EXTERNAL = "external"
    CHAT = "message"
    NOTICE = "notice"
    REQUEST = "request"
    META = "meta_event"
    SENT = "message_sent"  # 该类型不会被路由


class ServiceType(Enum):
    ADD_SCHEDULE = auto()  # AddScheduleArgs
    RM_SCHEDULE_BY_META = auto()  # meta_dict


class APSTriggerType(Enum):
    """不让子进程引用 `apscheduler`"""

    TIME_TRIGGER = auto()
    DATE_TRIGGER = auto()
    CORN_TRIGGER = auto()
    CALENDAR_INTERVAL_TRIGGER = auto()
    INTERVAL_TRIGGER = auto()


@define(slots=True)
class AddScheduleArgs:
    api_method: str
    api_kwargs: Mapping[str, Any]
    trigger: APSTriggerType
    trigger_kwargs: Mapping[str, Any]
    schedule_kwargs: Mapping[str, Any]


# endregion
@define(frozen=True, slots=True)
class User:
    platform: str
    user_id: str

    def __repr__(self):
        return f"{self.platform}(user={self.user_id})"


@define(frozen=True, slots=True)
class Group:
    platform: str
    group_id: str

    def __repr__(self):
        return f"{self.platform}(group={self.group_id})"
