import locale
import os
from collections import defaultdict
from collections.abc import Hashable, Iterable, Mapping, Sequence, Set
from copy import deepcopy
from dataclasses import fields as dc_fields
from dataclasses import is_dataclass
from datetime import date
from functools import wraps
from io import StringIO
from itertools import islice
from logging import getLevelNamesMapping, getLogger
from pathlib import Path
from sys import exit, _is_gil_enabled
from typing import TYPE_CHECKING, Any, Literal, SupportsIndex, overload

from aiofiles import open as aioopen
from anyio import Path as aioPath
from attrs import asdict, define, field
from attrs import fields as attrs_fields
from attrs import has
from pydantic import BaseModel
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedBase, CommentedMap, CommentedSeq, CommentedSet, comment_attrib
from ruamel.yaml.emitter import Emitter
from ruamel.yaml.representer import RoundTripRepresenter
from tenacity import _unset

from models.core import Group, User

from utils.aha import caller_aha_module  # , AHA_MODULE_PATTERN
from utils.aio import SingletonThreadSafeMeta, ThreadSafeMeta
from utils.container import SetList

from .bot_register import get_bot_class
from .i18n import _

try:
    from ctypes import windll
except ImportError:
    windll = None

__all__ = ("IndexedBotUser", "IndexedBotGroup", "Option", "cfg")

logger = getLogger(__name__)


@define(slots=True, frozen=True)
class IndexedBase:
    bot_index: SupportsIndex

    @property
    def platform(self):
        return get_bot_class(next(iter(cfg.bots[self.bot_index]))).platform


@define(slots=True, frozen=True)
class IndexedBotUser(IndexedBase):
    user_id: str = field(converter=str)

    def __eq__(self, other):
        if isinstance(other, User):
            return self.user_id == other.user_id and self.platform == other.platform
        if isinstance(other, IndexedBotUser):
            return super().__eq__(other)
        return NotImplemented

    def __hash__(self):
        return hash(User(self.platform, self.user_id))

    def __repr__(self):
        return f"{self.platform}(user={self.user_id})"


@define(slots=True, frozen=True)
class IndexedBotGroup(IndexedBase):
    group_id: str = field(converter=str)

    def __eq__(self, other):
        if isinstance(other, Group):
            return self.group_id == other.group_id and self.platform == other.platform
        if isinstance(other, IndexedBotGroup):
            return super().__eq__(other)
        return NotImplemented

    def __hash__(self):
        return hash(Group(self.platform, self.group_id))

    def __repr__(self):
        return f"{self.platform}(group={self.group_id})"


@define(slots=True)
class Option:
    """选项对象，用于处理带有选项注释的配置值"""

    options: Sequence = field(
        factory=SetList,
        converter=lambda x: SetList(x if isinstance(x, Iterable) and not isinstance(x, str) else (x,)),
    )
    value: str | int = None

    def __attrs_post_init__(self):
        if any(not isinstance(o, Config.BASE_TYPES) for o in self.options):
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
    def _setitem_single(self, idx, val):
        if isinstance(self[idx := idx.__index__()], Option) and not isinstance(val, Option):
            if val not in (opt_obj := self[idx]).options:
                raise ValueError(_("config.option.invalid") % (val, opt_obj.options))
            val = Option(opt_obj.options, val)
        super().__setitem__(idx, val)

    def __setitem__(self, index, value):
        # 如果原值是Option但新值不是，验证新值是否在选项内
        if isinstance(index, slice):
            indices = range(len(self))[index]
            for idx, val in zip(indices, value := tuple(value) if isinstance(value, Iterable) else [value] * len(indices)):
                self._setitem_single(idx, val)
        else:
            self._setitem_single(index, value)

    def __getitem__(self, index):
        return value.value if isinstance(value := super().__getitem__(index), Option) else value


@wraps(Emitter.choose_scalar_style)
def choose_scalar_style(self: Emitter):
    if not self.event.value and self.event.ctag.handle == "!!":
        return None
    if self.analysis is None:
        self.analysis = self.analyze_scalar(self.event.value)
    if self.event.style == '"' or self.canonical:
        return '"'
    if (self.event.implicit[0] or not self.event.implicit[2]) and (
        (not self.event.style or self.event.style == "?")
        and not (self.simple_key_context and (self.analysis.empty or self.analysis.multiline))
        and (self.flow_level and self.analysis.allow_flow_plain or (not self.flow_level and self.analysis.allow_block_plain))
        or self.event.style == "-"
    ):
        return ""
    self.analysis.allow_block = True
    if not self.flow_level and not self.simple_key_context:
        if self.event.style and self.event.style in "|>":
            return self.event.style
        elif self.analysis.multiline:
            return "|"
    if not self.event.style:
        if self.analysis.allow_double_quoted and "'" in self.event.value:
            return '"'
        return "'"
    if (
        self.event.style == "'"
        and self.analysis.allow_single_quoted
        and not (self.simple_key_context and self.analysis.multiline)
    ):
        return "'"
    return '"'


Emitter.choose_scalar_style = choose_scalar_style


class Config[
    TypeObj: type
    | type[Option]
    | tuple[type, type | tuple]
    | tuple[type, list[type | tuple]]
    | tuple[type, dict[Hashable, tuple[type | tuple, type | tuple]]]
](metaclass=SingletonThreadSafeMeta):
    BASE_TYPES = (str, int, float, type(None), date)

    __slots__ = (
        "_yaml",
        "_safe_yaml",
        "_data",
        "_old_data",
        "_config_file",
        "_default_types",
        "_default_used",
        "_modified",
        "_msg_prefix",
        "_group_blacklist",
        "_user_blacklist",
        "_group_whitelist",
        "_user_whitelist",
    )
    __thread_guarded_attrs__ = (
        "_data",
        "_default_types",
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
        self._config_file = aioPath(f"config.{os.getenv("BOT_ENV", "dev")}.yml")
        self._default_types = defaultdict(dict)
        self._default_used = False  # 初始化过值
        self._modified = []
        self._first_load()

        self._msg_prefix = {}
        self._group_blacklist = {}
        self._user_blacklist = {}
        self._group_whitelist = {}
        self._user_whitelist = {}

        self.bots  # 放到配置文件最前

    @ThreadSafeMeta.allow_non_main
    def __getitem__(self, key):
        return self.register(key, noneable=True, module=caller_aha_module() or "aha")

    def __setitem__(self, key: str, value):
        self.set(key, value, module=caller_aha_module(3))

    @ThreadSafeMeta.allow_non_main
    def get(self, key, default=None, module=None):
        try:
            return self.register(key, noneable=True, module=module or caller_aha_module())
        except KeyError:
            return default

    @ThreadSafeMeta.allow_non_main
    def __getattr__(self, key: str):
        if key.startswith("_"):
            raise AttributeError(key)
        return self.register(key, noneable=True, module=caller_aha_module() or "aha")

    def __setattr__(self, key: str, value):
        if key.startswith("_"):
            return super().__setattr__(key, value)
        self.set(key, value, module=caller_aha_module(3))

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
    def _transfer_comments(cls, source: Sequence | Mapping, target: CommentedBase):
        if ca := getattr(source, comment_attrib, None):
            setattr(target, comment_attrib, deepcopy(ca))
        for index, value in source.items() if isinstance(source, Mapping) else enumerate(source):
            if isinstance(value, Mapping):
                cls._transfer_comments(value, target[index])
            elif isinstance(value, Sequence) and not isinstance(value, str):
                cls._transfer_comments(value, target[index])

    def _first_load(self):
        if (path := Path(self._config_file)).exists():
            with open(path, "r", encoding="utf-8") as f:
                self._old_data = self._safe_yaml.load(f)
            if self._old_data is None:
                self._old_data = OptionCommentedMap()
                self._default_used = True
            # self.adjust_comments(self._old_data)
            self._data = self._convert_to_commented_containers(deepcopy(self._old_data))

    @ThreadSafeMeta.version_increment
    async def load(self):
        if not await self._config_file.exists():
            return
        try:
            async with aioopen(self._config_file, "r", encoding="utf-8") as f:
                self._old_data = self._safe_yaml.load(await f.read())
                if self._old_data is None:
                    self._old_data = OptionCommentedMap()
        except IOError:
            self._old_data = OptionCommentedMap()
        # self.adjust_comments(self._old_data)

        # 将程序修改的项合并到当前配置
        for module, key in self._modified:
            if (module_data := self._data.get(module)) and (key in module_data or module == "bots"):
                if module in self._old_data:
                    self._old_data[module][key] = module_data[key]
                else:
                    self._old_data[module] = module_data
        self._old_data = self._convert_to_commented_containers(self._old_data)
        self._transfer_comments(self._data, self._old_data)
        for k in islice(self._old_data, 1, None):
            self._comment_update(self._old_data, k, "\n")
        self._data = deepcopy(self._old_data)
        self._modified.clear()

        self._msg_prefix.clear()
        self._group_blacklist.clear()
        self._user_blacklist.clear()
        self._group_whitelist.clear()
        self._user_whitelist.clear()

    # endregion

    """
    @staticmethod
    def _check_permission(module, caller):
        if module and caller and module != "bots" and AHA_MODULE_PATTERN.match(caller):
            raise PermissionError(_("config.permission_denied"))
    """

    # region 数据类型处理
    @ThreadSafeMeta.allow_non_main
    @classmethod
    def _type2registed(cls, obj, ca_obj: CommentedBase | Option | Any, type_obj: TypeObj, index, noneable=True):
        """
        Args:
            ca_obj: 内容与 `obj` 相等，但若为可注释类型则比 `obj` 多注释信息。用于恢复注释。
            index: `obj` 在父级容器中的索引。
        """
        if obj is None:
            if noneable:
                return
            raise ValueError(f"Config value for index '{index}' cannot be null.")
        if type_obj is Option:
            if not ca_obj or obj in ca_obj.options:
                return obj
            raise ValueError(f"Config value for index '{index}' must be one of {ca_obj.options}.")
        try:
            if isinstance(type_obj, type):  # 基础类型和非唯一类型的 set
                return type_obj(obj)

            if isinstance(type_map := type_obj[1], (type, tuple)):  # 唯一类型的 set
                is_unique_ca = hasattr(ca_obj, "__len__") and len(ca_obj) == 1
                return type_obj[0](
                    cls._type2registed(v, ca_obj[0] if is_unique_ca else None if ca_obj is None else ca_obj[i], type_map, i)
                    for i, v in enumerate(obj)
                )

            if ca := getattr(ca_obj, comment_attrib, None):
                setattr(obj, comment_attrib, deepcopy(ca))  # 转移注释

            if obj.__class__ is OptionCommentedSeq:  # 序列
                unique_item_type_obj = type_map[0] if len(type_map) == 1 else None
                is_unique_ca = hasattr(ca_obj, "__len__") and len(ca_obj) == 1
                return type_obj[0](
                    cls._type2registed(
                        v,
                        ca_obj[0] if is_unique_ca else None if ca_obj is None else ca_obj[i],
                        unique_item_type_obj or type_map[i],
                        i,
                    )
                    for i, v in enumerate(obj)
                )
            # 映射与数据类
            unique_item_type_obj = next(iter(type_map.items()))[1] if len(type_map) == 1 else None
            new_obj = (obj_type if (is_mapping := issubclass(obj_type := type_obj[0], Mapping)) else dict)()
            for k, v in obj.items():
                items_type_obj = unique_item_type_obj or type_map[k]
                new_obj[cls._type2registed(k, None, items_type_obj[0], k)] = cls._type2registed(
                    v, ca_obj.get(k) if ca_obj else None, items_type_obj[1], k
                )
            if is_mapping:
                return new_obj
            if is_dataclass(obj_type):
                f = {f.name for f in dc_fields(obj_type)}
                return obj_type(**{k: v for k, v in new_obj.items() if k in f})
            if has(obj_type):
                f = {f.name for f in attrs_fields(obj_type)}
                return obj_type(**{k: v for k, v in new_obj.items() if k in f})
            if issubclass(obj_type, BaseModel):
                return obj_type.model_validate(new_obj)
        except TypeError as e:
            raise ValueError(f"Failed to convert the config value for index '{index}' to the required type.") from e

    @ThreadSafeMeta.allow_non_main
    @classmethod
    def _type2yaml(cls, obj, as_key=False, index=None, parent: CommentedBase = None) -> tuple[Any, TypeObj]:
        """
        Args:
            index: 若声明此参数则说明 obj 可能为 Option，此时一定作为映射的值或序列的元素。
            parent: 只有在 `index` 被声明了才可以声明。

        Returns:
            tuple: 转换后的值、原始类型 / tuple[原始类型, 元素类型字典]
        """
        if isinstance(obj, cls.BASE_TYPES):
            return obj, obj.__class__
        if isinstance(obj, aioPath):
            return str(obj), aioPath
        if isinstance(obj, Sequence):
            type_map = []
            if as_key:
                new_obj = []
            else:
                new_obj = OptionCommentedSeq()
                if ca := getattr(obj, comment_attrib, None):
                    setattr(new_obj, comment_attrib, ca := deepcopy(ca))
            for i, item in enumerate(obj):
                new_item, new_type = cls._type2yaml(item, as_key, i, new_obj)
                new_obj.append(new_item)
                type_map.append(new_type)
            return tuple(new_obj) if as_key else new_obj, (obj.__class__, type_map)
        if as_key:
            raise TypeError(f"Unsupported config key type: {obj.__class__.__name__}")

        if isinstance(obj, Option):
            if obj.options:
                parent.yaml_add_eol_comment(", ".join(str(opt) for opt in obj.options), index)
            return obj, Option
        if has(obj.__class__):
            new_obj, type_obj = cls._type2yaml(asdict(obj))
            return new_obj, (obj.__class__, type_obj[1])
        if isinstance(obj, BaseModel):
            new_obj, type_obj = cls._type2yaml(obj.model_dump())
            return new_obj, (obj.__class__, type_obj[1])
        if is_dataclass(obj):
            new_obj, type_obj = cls._type2yaml({field.name: getattr(obj, field.name) for field in dc_fields(obj)})
            return new_obj, (obj.__class__, type_obj[1])
        if isinstance(obj, Mapping):
            type_map = {}
            new_obj = OptionCommentedMap()
            if ca := getattr(obj, comment_attrib, None):
                setattr(new_obj, comment_attrib, ca := deepcopy(ca))
            for k in tuple(obj):
                new_k, new_k_type = cls._type2yaml(k, True)
                new_v, new_v_type = cls._type2yaml(obj[k], False, k, new_obj)
                new_obj[new_k] = new_v
                if ca and k is not new_k and (comments := ca._items.pop(k, None)):
                    ca._items[new_k] = comments
                type_map[new_k] = (new_k_type, new_v_type)
            return new_obj, (obj.__class__, type_map)
        if isinstance(obj, Set):
            if isinstance(obj, CommentedSet):
                raise TypeError("Unsupported config type: CommentedSet")
            new_obj = []
            unique_type, is_base = None, True
            for item in obj:
                new_item, new_type = cls._type2yaml(item)
                new_obj.append(new_item)
                if unique_type is None:
                    unique_type = item.__class__
                elif unique_type is False:
                    if is_base and isinstance(item, cls.BASE_TYPES):
                        continue
                    break
                elif unique_type is not item.__class__:
                    if is_base:
                        unique_type = False
                    else:
                        break
                if is_base and not isinstance(item, cls.BASE_TYPES):
                    is_base = False
            else:
                return new_obj, obj.__class__ if is_base else (obj.__class__, new_type)
            raise TypeError(f"Unsupported config set element type: {item.__class__.__name__}")
        raise TypeError(f"Unsupported config value type: {obj.__class__.__name__}")

    # endregion
    # region 设置项值
    @ThreadSafeMeta.version_increment
    def _set_value(self, key, value, module):
        # 存值
        self._data[module][key] = value
        self._modified.append((module, key))
        self._default_used = True

        # 清理对应缓存
        if key in self._USER_LIST_KEYS:
            self._user_blacklist.pop(module, None)
            self._user_whitelist.pop(module, None)
        if key in self._GROUP_LIST_KEYS:
            self._group_blacklist.pop(module, None)
            self._group_whitelist.pop(module, None)
        if key == "msg_prefix":
            self._msg_prefix.pop(module, None)

        return value.value if isinstance(value, Option) else value

    def set(self, key: str, value, module: str = None):
        """设置配置值"""
        # self._check_permission(module, caller)
        if not module:
            module = caller_aha_module(3)
        self._set_value(key, self._register(self._type2yaml(key, True)[0], value, module), module)

    # endregion
    # region 注册项
    @staticmethod
    def _comment_update(data: CommentedBase, key, value):
        if (comment_list := data.ca._items.get(key)) and (obj := comment_list[1]):
            if value == "\n" or obj[0].value[:-1] == value:
                return
            comment_list[1] = []
        data.yaml_set_comment_before_after_key(key, value, 0 if value == "\n" else 2)

    @ThreadSafeMeta.allow_non_main
    def _is_registered(self, key, module=None):
        return key in self._default_types[module]

    @ThreadSafeMeta.version_increment
    def _register(self, key, value, module, comment=None, is_default=False):
        """
        Args:
            key: 经过 `_type2yaml` 处理的。
            value: 未经过 `_type2yaml` 处理的。
        """
        if is_default and not isinstance(value, self.BASE_TYPES) and isinstance(value, (Sequence, Mapping, Set)) and not value:
            raise ValueError("Container in config default value must have at least one element")

        if not (mod_data := self._data.get(module)):
            self._data[module] = mod_data = OptionCommentedMap()

        # 添加注释
        if comment:
            self._comment_update(mod_data, key, comment)
        # if len(self._data) > 0 and mod != next(iter(self._data)):
        self._comment_update(self._data, module, "\n")

        result, self._default_types[module][key] = self._type2yaml(value, index=key, parent=mod_data)
        return result

    @ThreadSafeMeta.version_increment
    def set_comment(self, key: str, comment="", module: str = None):
        if not module:
            module = caller_aha_module(3)
        self._comment_update(self._data[module], key, comment)
        self._comment_update(self._data, module, "\n")

    if TYPE_CHECKING:

        @overload
        def register[T: Any | Option](
            self, key: str, default: T = _unset, comment=None, noneable: Literal[False] = False, module=None
        ) -> T: ...

        @overload
        def register[T: Any | Option](
            self, key: str, default: T, comment, noneable: Literal[True], module=None
        ) -> T | None: ...

        @overload
        def register[T: Any | Option](
            self, key: str, default: T = _unset, *, noneable: Literal[True], module=None
        ) -> T | None: ...

    @ThreadSafeMeta.allow_non_main
    def register(self, key, default=_unset, comment=None, noneable=False, module=None):
        """获取配置值，如果键值不存在则使用默认值初始化

        Args:
            default: 默认值
            comment: 注释
        """
        # if (storage_module := module or caller) is None:
        if (storage_module := module or caller_aha_module()) is None:
            raise RuntimeError(_("cannot_get_caller_aha_module"))

        # 获取配置
        key, value = self._type2yaml(key, True)[0], _unset
        for mod_name, mod_data in (("aha", aha_data := self._data.get("aha")), (storage_module, self._data.get(storage_module))):
            if mod_data and key in mod_data:
                if default is _unset:
                    if not self._is_registered(key, mod_name):
                        raise KeyError(key)
                    value = self._type2registed(mod_data[key], None, self._default_types[mod_name][key], key, noneable=noneable)
                else:
                    value = self._type2registed(
                        mod_data[key],
                        self._register(key, default, mod_name, comment, True),
                        self._default_types[mod_name][key],
                        key,
                        noneable,
                    )
                break

        if value is not _unset:
            return deepcopy(value)
        if (ee := self._data.get("expr_extractors")) and (ee := ee.get(key)) is not None:
            return ee == storage_module.removeprefix("modules.")
        if default is _unset:
            raise KeyError(key)

        # self._check_permission(module, caller)
        if aha_data and key in aha_data:
            raise KeyError(f"Key '{key}' is already registered in 'aha' config.")
        self._set_value(key, self._register(key, default, storage_module, comment, True), storage_module)
        return default

    # endregion
    async def reload_and_save(self):
        await self._config_file.parent.mkdir(parents=True, exist_ok=True)
        await self.load()
        async with aioopen(self._config_file, "w", encoding="utf-8") as f:
            self._yaml.dump(self._data, output := StringIO())
            await f.write(output.getvalue())

    @classmethod
    def _has_new_keys(cls, new_data, old_data):
        if new_data.__class__ is not old_data.__class__:
            return True

        if new_data.__class__ is OptionCommentedMap:
            for key in new_data:
                if key not in old_data:
                    return True
                if cls._has_new_keys(new_data[key], old_data[key]):
                    return True

        if new_data.__class__ is OptionCommentedSeq:
            if len(new_data) != len(old_data):
                return True
            for i in range(len(new_data)):
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

    """
    def clean(self):
        self._yaml = self._safe_yaml = self._old_data = self._data = self._config_file = self._default_types = (
            self._default_used
        ) = self._modified = self._msg_prefix = self._group_blacklist = self._user_blacklist = self._group_whitelist = (
            self._user_whitelist
        ) = None
    """

    # region 公共属性
    @property
    def super(self) -> tuple[User]:
        return self.get("super", module="aha")

    @property
    def global_msg_prefix(self) -> str | None:
        return self.get("global_msg_prefix", module="aha")

    @ThreadSafeMeta.allow_non_main
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
    def memory_level(self) -> Literal["low", "medium", "high"]:
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
    def execution_mode(self) -> Literal["async", "thread", "process"]:
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
    def _default_group_list_mode(self) -> Literal["blacklist", "whitelist"]:
        return self.get("default_group_list_mode", module="aha")

    @property
    def _default_group_list(self) -> frozenset[Group]:
        return self.get("default_group_list", module="aha")

    @property
    def _default_user_list_mode(self) -> Literal["blacklist", "whitelist"]:
        return self.get("default_user_list_mode", module="aha")

    @property
    def _default_user_list(self) -> frozenset[User]:
        return self.get("default_user_list", module="aha")

    _USER_LIST_KEYS = {"user_list_mode", "user_list"}
    _GROUP_LIST_KEYS = {"group_list_mode", "group_list"}

    @ThreadSafeMeta.allow_non_main
    def get_group_blacklist(self, module=None) -> frozenset[Group]:
        if not module:
            module = caller_aha_module()

        if (data := self._group_blacklist.get(module)) is not None:  # 缓存
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

    @ThreadSafeMeta.allow_non_main
    def get_group_whitelist(self, module=None) -> frozenset[Group]:
        if not module:
            module = caller_aha_module()

        if (data := self._group_whitelist.get(module)) is not None:  # 缓存
            return data
        if not module:  # 短路
            return self._default_group_list if self._default_group_list_mode == "whitelist" else frozenset()

        if (mode := (data := self._data.get(module, {})).get("group_list_mode")) is None:
            data = self._default_group_list if self._default_group_list_mode == "whitelist" else frozenset()
        else:
            data = frozenset(Group(**i) for i in data["group_list"]) if mode == "whitelist" else frozenset()
        self._group_whitelist[module] = data
        return data

    @ThreadSafeMeta.allow_non_main
    def is_group_enabled(self, platform: str, group_id: str, module=None):
        if l := cfg.get_group_blacklist(module or caller_aha_module()):
            return Group(platform, group_id) not in l
        return Group(platform, group_id) in cfg.get_group_whitelist(module or caller_aha_module())

    @ThreadSafeMeta.allow_non_main
    def get_user_blacklist(self, module=None) -> frozenset[User]:
        if not module:
            module = caller_aha_module()

        if (data := self._user_blacklist.get(module)) is not None:  # 缓存
            return data
        if not module:  # 短路
            return self._default_user_list if self._default_user_list_mode == "blacklist" else frozenset()

        # 获取
        if (mode := (data := self._data.get(module, {})).get("user_list_mode")) is None:
            data = self._default_user_list if self._default_user_list_mode == "blacklist" else frozenset()
        elif mode == "blacklist":
            data = {User(**i) for i in data["user_list"]}
            if self._default_user_list_mode == "blacklist":
                data.update(self._default_user_list)
                data = frozenset(data)
        else:
            data = frozenset()
        self._user_blacklist[module] = data
        return data

    @ThreadSafeMeta.allow_non_main
    def get_user_whitelist(self, module=None) -> frozenset[User]:
        if not module:
            module = caller_aha_module()

        if (data := self._user_whitelist.get(module)) is not None:  # 缓存
            return data
        if not module:  # 短路
            return self._default_user_list if self._default_user_list_mode == "whitelist" else frozenset()

        if (mode := (data := self._data.get(module, {})).get("user_list_mode")) is None:
            data = self._default_user_list if self._default_user_list_mode == "whitelist" else frozenset()
        else:
            data = frozenset(User(**i) for i in data["user_list"]) if mode == "whitelist" else frozenset()
        self._user_whitelist[module] = data
        return data

    @ThreadSafeMeta.allow_non_main
    def is_user_enabled(self, platform: str, user_id: str, module=None):
        if l := cfg.get_user_blacklist(module or caller_aha_module()):
            return User(platform, user_id) not in l
        return User(platform, user_id) in cfg.get_user_whitelist(module or caller_aha_module())

    @property
    def bots(self) -> Sequence[Mapping[str, Mapping]]:
        if "bots" not in self._data:
            self._data["bots"] = [
                {
                    "NapCat": {
                        "uri": "ws://127.0.0.1:3001",
                        "token": "napcat",
                        "start_server_command": (
                            r"""set "QQ=114514"
wmic process get CommandLine 2>nul | findstr /i /r /c:"QQNT\\QQ\.exe. --enable-logging -q %QQ%" >nul || start "" /d "\path\to\NapCat.Shell" launcher-user.bat %q%"""
                            if os.name == "nt"
                            else r"napcat start 114514"
                        ),
                        "stop_server_command": (
                            r"""for /f "tokens=*" %A in ('wmic process get CommandLine^,ProcessId 2^>nul ^| findstr /i /r /c:"QQNT\\QQ\.exe. --enable-logging -q 114514"') do if not defined TARGET_PID for %B in (%A) do set "TARGET_PID=%B"
if not defined TARGET_PID exit /b
taskkill /F /PID %TARGET_PID% 2>nul"""
                            if os.name == "nt"
                            else r"napcat stop 114514"
                        ),
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


cfg = Config()

cfg.bots
cfg.register(
    "execution_mode",
    Option(("async", "process") if _is_gil_enabled() else ("async", "thread", "process"), "async"),
    module="aha",
)
cfg.register(
    "lang",
    os.environ.get(
        "LANG", locale.windows_locale[windll.kernel32.GetUserDefaultLCID()] if windll else locale.getlocale()[0]
    ).split(".")[0],
    module="aha",
)
cfg.register("console_level", Option(getLevelNamesMapping(), "INFO"), module="log")
cfg.register("file_level", Option(getLevelNamesMapping(), "AHA_DEBUG"), module="log")
cfg.register("max_files", 5, module="log")
cfg.register("max_size", "16MiB", module="log")


def init_base_cfgs():
    cfg.set_comment(
        "execution_mode",
        f"""{_("config.comment.execution_mode.title")}
- 'async': {_("config.comment.execution_mode.async")}{"" if _is_gil_enabled() else f"\n- 'thread': {_("config.comment.execution_mode.thread")}"}
- 'process': {_("config.comment.execution_mode.process")}""",
        "aha",
    )
    cfg.set_comment("lang", _("config.comment.lang"), "aha")
    cfg.set_comment("console_level", _("config.comment.log.console.level"), "log")
    cfg.set_comment("file_level", _("config.comment.log.file.level"), "log")
    cfg.set_comment("max_files", _("config.comment.log.file.max_files"), "log")
    cfg.set_comment("max_size", _("config.comment.log.file.max_size"), "log")

    cfg.register("super", (User("QQ", "114514"),), "Super user ID.", module="aha")
    cfg.register("global_msg_prefix", "~", _("config.comment.global_msg_prefix"), True, "aha")
    database_def = CommentedMap(
        {"uri": "sqlite+aiosqlite:///data.db", "green": "sqlite:///data.db", "backup_dir": os.path.abspath("db_backup")}
    )
    database_def.yaml_set_comment_before_after_key("uri", _("config.comment.database"), 4)
    database_def.yaml_set_comment_before_after_key("green", _("config.comment.green_db"), 4)
    database_def.yaml_set_comment_before_after_key("backup_dir", _("config.comment.db_backup"), 4)
    cfg.register("database", database_def, module="aha")
    cfg.register("cache_conv", False, _("config.comment.cache_conv"), module="aha")
    cfg.register("memory_level", Option(("low", "medium", "high"), "medium"), _("config.comment.memory_level"), module="aha")
    cfg.register("base64_buffer", 1919810, _("config.comment.base64_buffer"), module="aha")
    cfg.register("bot_prefs", 1, _("config.comment.bot_prefs"), module="aha")
    cfg.register("file_msg_ttl", 3600, _("config.comment.file_msg_ttl"), module="cache")
    cfg.register("event", {"size": "16MiB", "ttl": 86400}, _("config.comment.event_cache"), module="cache")
    cfg.point_feat
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
    cfg.register("default_user_list", frozenset((User("NapCat", "114514"),)), module="aha")
    cfg.register("debug", False, _("config.comment.debug"), module="aha")
