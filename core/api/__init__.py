from functools import wraps
from types import FunctionType
from typing import get_overloads

from utils.misc import get_arg_names
from ..api_service import call_api
from ..i18n import _
from ..router import current_event
from .account import AccountAPI
from .group import GroupAPI
from .message import MessageAPI
from .private import PrivateAPI
from .support import SupportAPI


class APIMeta(type):
    def __new__(cls, name, bases, namespace, **kwargs):
        new_class = super().__new__(cls, name, bases, namespace, **kwargs)

        methods_to_wrap = {}
        for attr_name, attr_value in namespace.items():
            if not attr_name.startswith("__") and attr_value.__class__ is FunctionType:
                methods_to_wrap[attr_name] = attr_value

        # 父类
        for base in bases:
            for attr_name in dir(base):
                if not attr_name.startswith("__"):
                    if (attr_value := getattr(base, attr_name)).__class__ is FunctionType and attr_name not in methods_to_wrap:
                        methods_to_wrap[attr_name] = attr_value

        # 处理
        for attr_name, attr_value in methods_to_wrap.items():
            if get_overloads(attr_value):
                @wraps(attr_value)
                def wrapper(*args, __name=attr_name, __args=get_arg_names(attr_value), **kwargs):
                    if event := current_event.get():
                        if (value := getattr(event, "user_id", None)) is not None:
                            kwargs.setdefault("user_id", value)
                        if (value := getattr(event, "group_id", None)) is not None:
                            kwargs.setdefault("group_id", value)
                        kwargs.setdefault("bot", event.bot_id)
                    for i, arg in enumerate(args):
                        kwargs[__args[i + 2]] = arg
                    return call_api(__name, **kwargs)

            else:

                @wraps(attr_value)
                def wrapper(*args, __name=attr_name, **kwargs):
                    if not kwargs.get("bot"):
                        try:
                            kwargs["bot"] = current_event.get().bot_id
                        except LookupError as e:
                            raise RuntimeError(_("no_event_found_in_context")) from e
                    return call_api(__name, *args, **kwargs)

            setattr(new_class, attr_name, staticmethod(wrapper))

        return new_class


class API(AccountAPI, GroupAPI, MessageAPI, PrivateAPI, SupportAPI, metaclass=APIMeta):
    pass
