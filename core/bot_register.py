import sys
from contextlib import suppress

from .i18n import _

_class_registry: dict[str, type] = {}


def register(bot_class: type):
    _class_registry[bot_class.__name__] = bot_class
    return bot_class


def get_bot_class(class_name):
    if isinstance(class_name, type):
        class_name = class_name.__name__

    with suppress(KeyError):
        return _class_registry[class_name]

    from bots import BaseBot

    for module in sys.modules.values():
        if (candidate := getattr(module, class_name, None)) and issubclass(candidate, BaseBot):
            register(candidate)
            return candidate
    raise ValueError(_("router.get_class.404"))
