# from asyncio import Lock, get_running_loop
# from typing import Any
import os
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence, Set
from copy import deepcopy
from dataclasses import fields as dc_fields
from dataclasses import is_dataclass
from io import StringIO
from logging import getLevelNamesMapping, getLogger
from multiprocessing import current_process
from pathlib import Path
from sys import exit
from typing import Any

from aiofiles import open as aioopen
from anyio import Path as aioPath
from attrs import asdict, define, field
from attrs import fields as attrs_fields
from attrs import has
from pydantic import BaseModel
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedBase, CommentedMap, CommentedSeq
from ruamel.yaml.representer import RoundTripRepresenter
from tenacity import _unset

from models.core import Group, User
from models.metas import SingletonMeta

# from utils.misc import AHA_MODULE_PATTERN
from utils.misc import caller_aha_module, get_item_by_index

from .bot_register import get_bot_class
from .i18n import _

__all__ = ("IndexedBotUser", "IndexedBotGroup", "Option", "cfg")

logger = getLogger(__name__)


@define(slots=True, frozen=True)
class IndexedBotUser:
    bot_index: int = field(converter=int)
    user_id: str = field(converter=str)

    def __eq__(self, other):
        return (
            (self.user_id == other.user_id and self.platform == other.platform) if isinstance(other, User) else NotImplemented
        )

    def __hash__(self):
        return hash(User(self.platform, self.user_id))

    @property
    def platform(self):
        return get_bot_class(next(iter(cfg.bots[self.bot_index]))).platform

    def __repr__(self):
        return f"{self.platform}(user={self.user_id})"


@define(slots=True, frozen=True)
class IndexedBotGroup:
    bot_index: int = field(converter=int)
    group_id: str = field(converter=str)

    def __eq__(self, other):
        return (
            (self.group_id == other.group_id and self.platform == other.platform)
            if isinstance(other, Group)
            else NotImplemented
        )

    def __hash__(self):
        return hash(Group(self.platform, self.group_id))

    @property
    def platform(self):
        return get_bot_class(next(iter(cfg.bots[self.bot_index]))).platform

    def __repr__(self):
        return f"{self.platform}(group={self.group_id})"


@define(slots=True)
class Option:
    """选项对象，用于处理带有选项注释的配置值"""

    options: tuple = field(
        factory=tuple,
        converter=lambda x: (
            tuple(x) if isinstance(x, Iterable) and not isinstance(x, (str, bytes)) else (x,) if x is not None else ()
        ),
    )
    value: str | int = None

    def __attrs_post_init__(self):
        if any(not isinstance(o, (str, bytes, int, float, bool)) for o in self.options):
            raise ValueError("Options must be base types.")

        if self.value is None and self.options:
            object.__setattr__(self, "value", self.options[0])
        elif self.value not in self.options:
            raise ValueError(_("config.option.invalid") % (self.value, self.options))


class OptionCommentedMap(CommentedMap):
    def __setitem__(self, key, value):
        # 如果原值是Option但新值不是，验证新值是否在选项内
        if (old := self.get(key)) and isinstance(option_obj := old, Option) and not isinstance(value, Option):
            if value not in option_obj.options:
                raise ValueError(_("config.option.invalid") % (value, option_obj.options))
            value = Option(option_obj.options, value)
        super().__setitem__(key, value)

    def __getitem__(self, key):
        return value.value if isinstance(value := super().__getitem__(key), Option) else value

    def get(self, key, default=None):
        return value.value if isinstance(value := super().get(key, default), Option) else value


class OptionCommentedSeq(CommentedSeq):
    """支持Option对象的CommentedSeq子类"""

    def __setitem__(self, index, value):
        # 如果原值是Option但新值不是，验证新值是否在选项内
        if isinstance(index, int) and index < len(self) and isinstance(self[index], Option) and not isinstance(value, Option):
            if value not in (option_obj := self[index]).options:
                raise ValueError(_("config.option.invalid") % (value, option_obj.options))
            value = Option(option_obj.options, value)
        super().__setitem__(index, value)

    def __getitem__(self, index):
        return value.value if isinstance(value := super().__getitem__(index), Option) else value


class Config(metaclass=SingletonMeta):
    BASE_TYPES = {str, bytes, int, float, bool}

    __slots__ = (
        "_yaml",
        "_safe_yaml",
        "_data",
        "_old_data",
        "_lock",
        "_config_file",
        "_loaded",
        "_default_types",
        "_default_used",
        "_modified",
        "_msg_prefix",
        "_group_blacklist",
        "_user_blacklist",
        "_group_whitelist",
        "_user_whitelist",
    )

    def __init__(self):
        self._yaml = YAML()
        self._safe_yaml = YAML(typ="safe")
        self._yaml.representer.add_representer(OptionCommentedMap, RoundTripRepresenter.represent_dict)
        self._yaml.representer.add_representer(OptionCommentedSeq, RoundTripRepresenter.represent_list)
        self._old_data = {}
        self._data = CommentedMap()
        # self._lock = Lock()
        self._config_file = aioPath(f"config.{os.getenv("BOT_ENV", "dev")}.yml")
        self._loaded = False
        self._default_types = defaultdict(dict)
        self._default_used = False  # 初始化过值
        self._modified = []
        self._load()

        self._msg_prefix = {}
        self._group_blacklist = {}
        self._user_blacklist = {}
        self._group_whitelist = {}
        self._user_whitelist = {}

        self.bots  # 先把这个写了

    def __getitem__(self, key):
        return self.register(key, module=caller_aha_module())

    def __setitem__(self, key: str, value):
        self.set(key, value, module=caller_aha_module())

    def get(self, key, default=None, module=None):
        try:
            return self.register(key, module=module or caller_aha_module())
        except KeyError:
            return default

    def __getattr__(self, key: str):
        if key.startswith("_"):
            raise AttributeError(key)
        return self.register(key, module=caller_aha_module())

    def __setattr__(self, key: str, value):
        if key.startswith("_"):
            return super().__setattr__(key, value)
        self.set(key, value, module=caller_aha_module())

    # region 读取文件
    @classmethod
    def _convert_to_commented_containers(cls, obj):
        if isinstance(obj, Mapping):
            if obj.__class__ is not OptionCommentedMap:
                obj = OptionCommentedMap(obj)
            for k, v in obj.items():
                obj[k] = cls._convert_to_commented_containers(v)
        elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes)):
            if obj.__class__ is not OptionCommentedSeq:
                obj = OptionCommentedSeq(obj)
            for i, item in enumerate(obj):
                obj[i] = cls._convert_to_commented_containers(item)
        return obj

    """
    @staticmethod
    def _adjust_commented_comment(parent_items, key, child: CommentedBase):
        \"""
        Returns:
            CommentToken: 子字典最后一个键的右侧注释
        \"""
        if not (parent_items and (child_ca := child.ca).comment and key in parent_items):
            return
        if (comment := parent_items[key][3][0]) != child_ca.comment[1][0]:  # 3 下行
            return

        # 清除原注释
        parent_items[key][3] = child_ca.comment = None  # 3 下行
        if not child:
            return

        child_items: dict = child_ca._items
        if isinstance(child, CommentedMap):
            last_key = None
            for k in child:
                v = child_items.setdefault(k, [None, None, None, None])
                if last_key and (comment := (last_v := child_items[last_key])[2]):  # 2 右侧
                    comment.value = comment.value.lstrip()
                    v[1] = [comment]  # 1 上行
                    last_v[2] = None  # 2 右侧
                else:
                    v[1] = [comment]  # 1 上行
                    last_v = v
                last_key = k
        else:
            for k, _ in enumerate(child):
                v = child_items.setdefault(k, [None, None, None, None])
                if k > 0:
                    comment = (last_v := child_items[k - 1])[2]  # 2 右侧
                    comment.value = comment.value.lstrip()
                    v[1] = [comment]  # 1 上行
                    last_v[2] = None  # 2 右侧
                else:
                    v[1] = [comment]  # 1 上行
                    last_v = v

        # 返回最后一个键的右侧注释，转移至父字典键的上行
        if last_comment := last_v[2]:
            last_comment.value = f"\n{last_comment.value.lstrip()}"
        last_v[2] = None
        return last_comment

    @classmethod
    def adjust_comments(cls, data: CommentedBase | Mapping | Sequence):
        \"""
        将父字典的键下行注释和子字典开始注释转为子字典第一个键的上行注释
        将子字典所有键的下行注释转为下一个键的上行注释
        \"""
        if isinstance(data, CommentedMap):
            items: dict = data.ca._items
            last_comment = None
            for key, value in data.items():
                if last_comment:
                    items.setdefault(key, [None, None, None, None])[1] = [last_comment]  # 1 上行
                last_comment = cls._adjust_commented_comment(items, key, value) if isinstance(value, CommentedBase) else None
                cls.adjust_comments(value)
        elif isinstance(data, CommentedSeq):
            items = data.ca._items
            last_comment = None
            for idx, value in enumerate(data):
                if last_comment:
                    items.setdefault(idx, [None, None, None, None])[1] = [last_comment]  # 1 上行
                last_comment = cls._adjust_commented_comment(items, idx, value) if isinstance(value, CommentedBase) else None
                cls.adjust_comments(value)
        elif isinstance(data, Sequence) and not isinstance(data, (bytes, str)):
            for item in data:
                cls.adjust_comments(item)
        elif isinstance(data, Mapping):
            for value in data.values():
                cls.adjust_comments(value)
    """

    @classmethod
    def _transfer_comments(cls, source: Sequence | Mapping, target: Sequence | Mapping):
        is_commented = isinstance(source, CommentedBase)
        if is_commented or isinstance(source, (Mapping, Sequence)) and not isinstance(source, (str, bytes)):
            if ca := getattr(source, "_yaml_comment", None):
                target._yaml_comment = ca
            for key, value in source.items():
                if isinstance(value, Mapping):
                    cls._transfer_comments(value, target[key])
                elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                    for i, item in enumerate(value):
                        cls._transfer_comments(item, target[key][i])

    def _load(self):
        if (path := Path(self._config_file)).exists():
            with open(path, "r", encoding="utf-8") as f:
                self._old_data = self._safe_yaml.load(f)
            if self._old_data is None:
                self._old_data = OptionCommentedMap()
                self._default_used = True
            # self.adjust_comments(self._old_data)

        if self._loaded:
            # 将程序修改的项合并到当前配置
            for module, key in self._modified:
                if (module_data := self._data.get(module)) and key in module_data:
                    if module in self._old_data:
                        self._old_data[module][key] = module_data[key]
                    else:
                        self._old_data[module] = module_data
            self._old_data = self._convert_to_commented_containers(self._old_data)
            self._transfer_comments(self._data, self._old_data)
            self._data = deepcopy(self._old_data)
            self._modified.clear()

            self._msg_prefix.clear()
            self._group_blacklist.clear()
            self._user_blacklist.clear()
            self._group_whitelist.clear()
            self._user_whitelist.clear()
        else:
            self._data = self._convert_to_commented_containers(deepcopy(self._old_data))
            self._loaded = True

    async def load(self):
        if await self._config_file.exists():
            async with aioopen(self._config_file, "r", encoding="utf-8") as f:
                self._old_data = self._safe_yaml.load(await f.read())
            if self._old_data is None:
                self._old_data = {}
            # self.adjust_comments(self._old_data)

        if self._loaded:
            # 将程序修改的项合并到当前配置
            for module, key in self._modified:
                if (module_data := self._data.get(module)) and (key in module_data or module == "bots"):
                    if module in self._old_data:
                        self._old_data[module][key] = module_data[key]
                    else:
                        self._old_data[module] = module_data
            self._old_data = self._convert_to_commented_containers(self._old_data)
            self._transfer_comments(self._data, self._old_data)
            self._data = deepcopy(self._old_data)
            self._modified.clear()

            self._msg_prefix.clear()
            self._group_blacklist.clear()
            self._user_blacklist.clear()
            self._group_whitelist.clear()
            self._user_whitelist.clear()
        else:
            self._data = self._convert_to_commented_containers(deepcopy(self._old_data))
            self._loaded = True

    # endregion

    """
    @staticmethod
    def _check_permission(module, caller):
        if module and caller and module != "bots" and AHA_MODULE_PATTERN.match(caller):
            raise PermissionError(_("config.permission_denied"))
    """

    # region 数据类型处理
    @classmethod
    def _loads(cls, obj, key, type_map: dict[str, type | tuple], ca_obj, noneable=True):
        """类型转换"""
        try:
            target_type = get_item_by_index(type_map, 0)[1] if len(type_map) == 1 else type_map.get(key)
            if obj is None:
                if noneable:
                    return None
                raise ValueError(f"Config value for key '{key}' cannot be null.")
            if target_type and obj.__class__ in cls.BASE_TYPES:
                return target_type(obj)
            if obj.__class__ is OptionCommentedMap:
                if isinstance(ca_obj, CommentedMap):
                    cls._transfer_comments(ca_obj, obj)
                if target_type.__class__ is dict:
                    return {
                        k: cls._loads(v, k, target_type, ca_obj.get(k) if isinstance(ca_obj, Mapping) else None)
                        for k, v in obj.items()
                    }
                if has(target_type):
                    f = {f.name for f in attrs_fields(target_type)}
                    return target_type(**{k: v for k, v in obj.items() if k in f})
                if issubclass(target_type, BaseModel):
                    return target_type.model_validate(obj)
                if is_dataclass(target_type):
                    f = {f.name for f in dc_fields(target_type)}
                    return target_type(**{k: v for k, v in obj.items() if k in f})
            if obj.__class__ is OptionCommentedSeq and (target_type := type_map[key]).__class__ is tuple:
                if isinstance(ca_obj, CommentedSeq):
                    cls._transfer_comments(ca_obj, obj)
                return target_type[0](
                    cls._loads(item, i, target_type[1], ca_obj[i] if isinstance(ca_obj, Sequence) and len(ca_obj) > i else None)
                    for i, item in enumerate(obj)
                )
            return None
        except TypeError as e:
            raise ValueError(f"Failed to convert the config value for key '{key}' to the required type.") from e

    @classmethod
    def _dumps(cls, obj, parent: OptionCommentedMap | OptionCommentedSeq, index, type_map: dict):
        """记录原始类型并返回可安全序列化的类型"""
        if isinstance(obj, (str, bytes, int, float, bool, type(None))):
            type_map[index] = obj.__class__
            return obj
        if isinstance(obj, Option):
            if obj.options:
                parent.yaml_add_eol_comment(", ".join(str(opt) for opt in obj.options), index)
            type_map[index] = obj.value.__class__
            return obj
        if has(obj.__class__):
            type_map[index] = obj.__class__
            return asdict(obj)
        if isinstance(obj, BaseModel):
            type_map[index] = obj.__class__
            return obj.model_dump()
        if is_dataclass(obj):
            type_map[index] = obj.__class__
            return {field.name: getattr(obj, field.name) for field in dc_fields(obj)}
        if isinstance(obj, Mapping):
            types = type_map[index] = {}
            processed_dict = obj if isinstance(obj, CommentedMap) else OptionCommentedMap()
            for key, value in obj.items():
                if not isinstance(key, str):
                    raise TypeError(f"Key must be str, not {key.__class__.__name__}")
                processed_dict[key] = cls._dumps(value, obj, key, types)
            return processed_dict
        if isinstance(obj, (Sequence, Set)):
            type_map[index] = (obj.__class__, types := {})
            processed_list = obj if isinstance(obj, CommentedSeq) else OptionCommentedSeq()
            for i, item in enumerate(obj):
                processed_list.append(cls._dumps(item, obj, i, types))
            return processed_list
        if isinstance(obj, aioPath):
            type_map[index] = aioPath
            return str(obj)
        raise TypeError(f"Unsupported config value type: {obj.__class__.__name__}")

    # endregion
    # region 设置项值
    def _set_value(self, key, value, module):
        # 存值
        self._data[module][key] = value
        self._modified.append((module, key))
        self._default_used = True

        return value.value if isinstance(value, Option) else value

    def set[T: Any | Option](self, key: str, value: T, module: str = None) -> T:
        """设置配置值"""
        # self._check_permission(module, caller)
        if not module:
            module = caller_aha_module()
        return self._set_value(key, self._register(key, value, module), module)

    # endregion
    # region 注册项
    @staticmethod
    def _comment_update(data: CommentedBase, key, value):
        if (comment_list := data.ca._items.get(key)) and (obj := comment_list[1]):
            if value == "\n" or obj[0].value[:-1] == value:
                return
            comment_list[1] = []
        data.yaml_set_comment_before_after_key(key, value, 0 if value == "\n" else 2)

    def _is_registered(self, key: str, module: str = None):
        return key in self._default_types[module]

    def _register(self, key, default, module, comment=None):
        if not (mod_data := self._data.get(module)):
            self._data[module] = mod_data = OptionCommentedMap()

        # 添加注释
        if comment:
            self._comment_update(mod_data, key, comment)
        # if len(self._data) > 0 and mod != next(iter(self._data)):
        self._comment_update(self._data, module, "\n")

        if isinstance(default, Option) and key in mod_data and (value := mod_data[key]) not in default.options:
            self._set_value(key, default, module)
            logger.warning(
                _("config.not_in_options")
                % {"mod": module, "key": key, "value": value, "options": " ".join(default.options), "def": default.value}
            )
        return self._dumps(default, mod_data, key, self._default_types[module])

    """
    TODO: 使用异步锁而不是像现在依赖内部锁。
    async def register_async[T: Any | Option](self, key: str, default: T = None, comment: str = None, module: str = None) -> T:
        async with self._lock:
            return self.register(key, default, comment, module=module)

    def register[T: Any | Option](self, key: str, default: T = None, comment: str = None, module: str = None) -> T:
        if get_running_loop():
            raise RuntimeError(_("config.green_in_aio"))
        return self._register(key, default, comment, module=module)
    """

    def register[T: Any | Option](self, key, default: T = _unset, comment=None, noneable=False, module=None) -> T | None:
        """获取配置值，如果键值不存在则使用默认值初始化

        Args:
            default: 默认值
            comment: 注释
        """
        # if (storage_module := module or caller) is None:
        if (storage_module := module or caller_aha_module()) is None:
            return

        # 获取配置
        value = _unset
        for mod in {"aha", storage_module}:
            if (data := self._data.get(mod)) and key in data:
                if default is _unset:
                    if not self._is_registered(key, mod):
                        raise KeyError(key)
                else:
                    self._register(key, default, mod, comment)
                value = self._loads(value := data[key], key, self._default_types[mod], default, noneable)

        if value is not _unset:
            return value
        if (ee := self._data.get("expr_extractors")) and (ee := ee.get(key)) is not None:
            return ee == storage_module.removeprefix("modules.")
        if default is _unset:
            raise KeyError(key)

        # self._check_permission(module, caller)
        return self._set_value(key, self._register(key, default, storage_module, comment), storage_module)

    # endregion
    async def reload_and_save(self):
        await self._config_file.parent.mkdir(parents=True, exist_ok=True)
        await self.load()
        async with aioopen(self._config_file, "w", encoding="utf-8") as f:
            self._yaml.dump(self._data, output := StringIO())
            await f.write(output.getvalue())

    @classmethod
    def _has_new_keys(cls, new_data, old_data):
        if (data_type := new_data.__class__) is not old_data.__class__:
            return True

        if data_type is OptionCommentedMap:
            for key in new_data:
                if key in old_data:
                    return True
                if cls._has_new_keys(new_data[key], old_data[key]):
                    return True

        if data_type is OptionCommentedSeq:
            if len(new_data) != len(old_data):
                return True
            for i in new_data:
                if cls._has_new_keys(new_data[i], old_data[i]):
                    return True

        return False

    async def finalize_initialization(self):
        if not self._default_used:
            for module, key in self._modified:
                if self._has_new_keys(self._data[module][key], self._old_data.get(module, {}).get(key, None)):
                    self._default_used = True
                    break

        if self._default_used:
            await self.reload_and_save()
            self._old_data = None
            logger.warning(_("config.new"))
            exit(78)
        self._old_data = None

    def clean(self):
        self._yaml = self._safe_yaml = self._old_data = self._data = self._config_file = self._default_types = self._loaded = (
            self._default_used
        ) = self._modified = self._msg_prefix = self._group_blacklist = self._user_blacklist = self._group_whitelist = (
            self._user_whitelist
        ) = None

    # region 公共属性
    @property
    def super(self) -> tuple[User]:
        return self.get("super", module="aha")

    @property
    def global_msg_prefix(self) -> str | None:
        return self.get("global_msg_prefix", module="aha")

    def get_msg_prefix(self, module: str = None) -> str | None:
        """若只有单特殊字符则返回半角"""
        if not module:
            module = caller_aha_module()

        if data := self._msg_prefix.get(module):  # 缓存
            return data

        if module and "msg_prefix" in (data := self._data.get(module, {})):
            data = data["msg_prefix"]
        else:
            data = self.global_msg_prefix

        if data and len(data) == 1:
            from utils.string import halfwidth

            data = halfwidth(data)

        self._msg_prefix[module] = data
        return data

    @property
    def database(self) -> dict:
        return self.get("database", module="aha")

    @property
    def lang(self) -> str:
        return self.get("lang", module="aha")

    @property
    def point_feat(self):
        return self.register("point_feat", False, _("config.comment.point_feat"), module="aha")

    @property
    def memory_level(self) -> str:
        return self.get("memory_level", module="aha")

    @property
    def base64_buffer(self) -> int:
        return self.get("base64_buffer", module="aha")

    @property
    def playwright(self):
        return self.register("playwright", False, _("config.comment.playwright"), module="aha")

    @property
    def cache_conv(self) -> bool:
        return self.get("cache_conv", module="aha")

    @property
    def execution_mode(self) -> str:
        return self.get("execution_mode", module="aha")

    @property
    def bot_prefs(self) -> int:
        return self.get("bot_prefs", module="aha")

    @property
    def file_msg_ttl(self) -> int:
        return self.get("file_msg_ttl", module="cache")

    @property
    def event_cache(self) -> dict:
        return self.get("event", module="cache")

    @property
    def debug(self) -> bool:
        return self.get("debug", module="aha")

    @property
    def _default_group_list_mode(self) -> str:
        return self.get("default_group_list_mode", module="aha")

    @property
    def _default_group_list(self) -> frozenset[Group]:
        return self.get("default_group_list", module="aha")

    @property
    def _default_user_list_mode(self) -> str:
        return self.get("default_user_list_mode", module="aha")

    @property
    def _default_user_list(self) -> frozenset[User]:
        return self.get("default_user_list", module="aha")

    def get_group_blacklist(self, module=None) -> frozenset[Group]:
        if not module:
            module = caller_aha_module()

        if data := self._group_blacklist.get(module):  # 缓存
            return data
        if not module:  # 短路
            return self._default_group_list if self._default_group_list_mode == "blacklist" else frozenset()

        # 获取
        if (mode := (data := self._data.get(module, {})).get("group_list_mode")) is None:
            data = self._default_group_list if self._default_group_list_mode == "blacklist" else frozenset()
        elif mode == "blacklist":
            data = {Group(**i) for i in data["group_list"]}
            if self._default_group_list_mode == "blacklist":
                data.update(self._default_group_list)
                data = frozenset(data)
        else:
            data = frozenset()
        self._group_blacklist[module] = data
        return data

    def get_group_whitelist(self, module=None) -> frozenset[Group]:
        if not module:
            module = caller_aha_module()

        if data := self._group_whitelist.get(module):  # 缓存
            return data
        if not module:  # 短路
            return self._default_group_list if self._default_group_list_mode == "whitelist" else frozenset()

        if (mode := (data := self._data.get(module, {})).get("group_list_mode")) is None:
            data = self._default_group_list if self._default_group_list_mode == "whitelist" else frozenset()
        else:
            data = frozenset(Group(**i) for i in data["group_list"]) if mode == "whitelist" else frozenset()
        self._group_whitelist[module] = data
        return data

    def get_user_blacklist(self, module=None) -> frozenset[User]:
        if not module:
            module = caller_aha_module()

        if data := self._user_blacklist.get(module):  # 缓存
            return data
        if not module:  # 短路
            return self._default_user_list if self._default_user_list_mode == "blacklist" else frozenset()

        # 获取
        if (mode := (data := self._data.get(module, {})).get("user_list_mode")) is None:
            data = self._default_user_list if self._default_user_list_mode == "blacklist" else frozenset()
        elif mode == "blacklist":
            data = {User(**i) for i in data["group_list"]}
            if self._default_user_list_mode == "blacklist":
                data.update(self._default_user_list)
                data = frozenset(data)
        else:
            data = frozenset()
        self._user_blacklist[module] = data
        return data

    def get_user_whitelist(self, module=None) -> frozenset[User]:
        if not module:
            module = caller_aha_module()

        if data := self._user_whitelist.get(module):  # 缓存
            return data
        if not module:  # 短路
            return self._default_user_list if self._default_user_list_mode == "whitelist" else frozenset()

        if (mode := (data := self._data.get(module, {})).get("user_list_mode")) is None:
            data = self._default_user_list if self._default_user_list_mode == "whitelist" else frozenset()
        else:
            data = frozenset(User(**i) for i in data["group_list"]) if mode == "whitelist" else frozenset()
        self._user_whitelist[module] = data
        return data

    @property
    def bots(self) -> Sequence[Mapping[str, Mapping]]:
        if "bots" not in self._data:
            self._data["bots"] = self._old_data["bots"] = [
                {
                    "NapCat": {
                        "uri": "ws://127.0.0.1:3000",
                        "token": "napcat",
                        "start_server_command": "",
                        "retry_config": {"wait_exponential": {"multiplier": 1, "max": 30, "exp_base": 2, "min": 1}},
                        "lang": "zh_CN",
                    }
                }
            ]
            self._modified.append(("bots", None))
            self._default_used = True
        return self._data["bots"]

    @property
    def console_log_level(self) -> str:
        return self.get("console_level", module="log")

    @property
    def file_log_level(self) -> str:
        return self.get("file_level", module="log")

    @property
    def max_log_files(self) -> int:
        return self.get("max_files", module="log")

    @property
    def log_file_max_size(self) -> str:
        return self.get("max_size", module="log")

    # endregion


if current_process().name == "MainProcess":
    cfg = Config()

    cfg.bots
    cfg.register(
        "execution_mode",
        # Option(("async", "process") if sys._is_gil_enabled() else ("async", "thread", "process")),
        Option(("async", "process")),
        """Defines the execution mode for API services and module callbacks in the framework.
- 'async': All API services and module callbacks share a single thread.
- 'process': Each API service runs in its own process, all module callbacks share a single thread.""",
        module="aha",
    )
    """
    - 'thread': Each API service runs in its own thread, module callbacks use an asynchronous loop pool. (no-gil only)
    - 'thread-pool': Both API services and module callbacks use an asynchronous loop pool. (no-gil only)
    """
    cfg.register("lang", os.environ.get("LANG", "en_US").split(".")[0], "Default language.", module="aha")
    cfg.register("console_level", Option(getLevelNamesMapping(), "INFO"), "Console log level.", module="log")
    cfg.register("file_level", Option(getLevelNamesMapping(), "AHA_DEBUG"), "File log level.", module="log")
    cfg.register("max_files", 5, "Maximum number of log files.", module="log")
    cfg.register("max_size", "16MiB", "Maximum size per log file.", module="log")

    def init_base_cfgs():
        cfg.register("super", (User("QQ", "114514"),), "Super user ID.", module="aha")
        cfg.register("global_msg_prefix", "~", _("config.comment.global_msg_prefix"), True, "aha")
        database_def = OptionCommentedMap(
            {"uri": "sqlite+aiosqlite:///data.db", "green": "sqlite:///data.db", "backup_dir": os.path.abspath("db_backup")}
        )
        database_def.yaml_set_comment_before_after_key("uri", _("config.comment.database"), 4)
        database_def.yaml_set_comment_before_after_key("green", _("config.comment.green_db"), 4)
        database_def.yaml_set_comment_before_after_key("backup_dir", _("config.comment.db_backup"), 4)
        cfg.register("database", database_def, module="aha")
        cfg.register("cache_conv", False, _("config.comment.cache_conv"), module="aha")
        cfg.register(
            "memory_level", Option(("low", "medium", "high"), "medium"), _("config.comment.memory_level"), module="aha"
        )
        cfg.register("base64_buffer", 1919810, _("config.comment.base64_buffer"), module="aha")
        cfg.register("bot_prefs", 1, _("config.comment.bot_prefs"), module="aha")
        cfg.register("file_msg_ttl", 3600, _("config.comment.file_msg_ttl"), module="cache")
        cfg.register("event", {"size": "16MiB", "ttl": 86400}, _("config.comment.event_cache"), module="cache")
        cfg.register(
            "default_group_list_mode",
            Option(("whitelist", "blacklist")),
            _("config.comment.default_group_list_mode"),
            module="aha",
        )
        cfg.register("default_group_list", frozenset((Group("NapCat", "1919810"),)), module="aha")
        cfg.register(
            "default_user_list_mode",
            Option(("whitelist", "blacklist")),
            _("config.comment.default_user_list_mode"),
            module="aha",
        )
        cfg.register("default_user_list", frozenset(), module="aha")
        cfg.register("debug", False, _("config.comment.debug"), module="aha")
