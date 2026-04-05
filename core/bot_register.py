from .i18n import _

_class_registry: dict[str, type] = {}


def register(bot_class: type):
    _class_registry[bot_class.__name__] = bot_class
    return bot_class


def get_bot_class(class_name):
    if isinstance(class_name, type):
        class_name = class_name.__name__
    try:
        return _class_registry[class_name]
    except KeyError:
        raise ValueError(_("router.get_class.404"))
