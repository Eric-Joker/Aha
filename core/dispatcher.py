from asyncio import create_task
from collections import defaultdict, deque
from collections.abc import Callable, Container, Hashable, Sequence
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from functools import wraps
from logging import getLogger
from re import Match, Pattern
from sys import _getframe
from typing import TYPE_CHECKING, Any, get_type_hints, overload

from pydantic import TypeAdapter
from tenacity import _unset

from models.api import BaseEvent, External, Message, MetaEvent, Notice, Request
from models.core import EventCategory
from models.msg import MessageChain, MsgSeg
from utils.aha import FULL_AHA_MODULE_PATTERN, caller_aha_module
from utils.aio import ThreadSafeAsyncMeta, async_run_func
from utils.container import DefaultIndexedDict, IndexedDict
from utils.func import get_arg_names, get_true_func

from . import status
from .config import cfg
from .expr import (
    PM,
    And,
    Apply,
    Call,
    Expr,
    GetAttr,
    binary_expr_exists,
    build_cond,
    cprmc,
    cprms,
    evaluate,
    field_exists,
    remove_msg_seq_prefix,
)
from .i18n import _, create_translator

__all__ = ("on_message", "on_notice", "on_request", "on_meta", "on_start", "on_cleanup", "clear_handlers", "help_items")

_logger = getLogger("AHA (Dispatcher)")


# region 回调容器
@dataclass(slots=True)
class ExprAttach:
    aha_module: str
    threadable: bool
    need_isolation: bool = False
    pre_hook: Callable[[MessageChain], MessageChain] = None
    use_global_prefix: bool = False

    def __post_init__(self):
        if self.pre_hook:
            self.need_isolation = True


class ExprPoolNode[Key: Hashable | Expr]:
    __slots__ = ("key", "value", "token", "attach", "prev", "next")

    def __init__(self, key, value, token, attach):
        self.key: Key = key
        self.value: Callable = value
        self.token: int = token
        self.attach: ExprAttach = attach
        self.prev: ExprPoolNode[Key] | None = None
        self.next: ExprPoolNode[Key] | None = None


class ExprPool[Key: Hashable | Expr](Container[tuple[Key, Callable, ExprAttach | None]]):
    __slots__ = ("_head", "_tail", "token_map", "_key_nodes")

    def __init__(self):
        self._head: ExprPoolNode[Key] | None = None
        self._tail: ExprPoolNode[Key] | None = None
        self.token_map: IndexedDict[int, ExprPoolNode[Key]] = IndexedDict()
        self._key_nodes: defaultdict[Key, set[ExprPoolNode[Key]]] = defaultdict(set)

    def __len__(self):
        return len(self.token_map)

    def __contains__(self, key: Key):
        return key in self._key_nodes

    def __iter__(self):
        current = self._tail  # 从尾部开始倒序遍历
        while current is not None:
            yield current.key, current.value, current.token, current.attach
            current = current.prev

    def add(self, key: Key, value: Callable, attach: ExprAttach = None):
        node = ExprPoolNode(key, value, token := (self.token_map.key_at(-1) + 1) if self.token_map else 0, attach)

        # 添加到链表尾部
        if self._tail is None:
            self._head = self._tail = node
        else:
            node.prev = self._tail
            self._tail.next = node
            self._tail = node

        self.token_map[token] = node
        self._key_nodes[key].add(node)
        return token

    def remove(self, token):
        if (node := self.token_map.pop(token, None)) is None:
            return

        # 从链中移除节点
        if node.prev:
            node.prev.next = node.next
        else:
            self._head = node.next
        if node.next:
            node.next.prev = node.prev
        else:
            self._tail = node.prev

        # 从容器中移除
        (nodes := self._key_nodes[node.key]).discard(node)
        if not nodes:
            del self._key_nodes[node.key]

    def remove_key(self, key: Key):
        if key not in self._key_nodes:
            return

        for node in self._key_nodes.pop(key):
            # 从链中移除
            if node.prev:
                node.prev.next = node.next
            else:
                self._head = node.next
            if node.next:
                node.next.prev = node.prev
            else:
                self._tail = node.prev

            self.token_map.pop(node.token, None)

    def clear(self):
        """移除所有没有exp属性的key"""
        for key in [key for key in self._key_nodes if not getattr(key, "_exp", None)]:
            self.remove_key(key)


# endregion
@dataclass
class CallbackMeta:
    args: frozenset
    pool: ExprPool
    condition: Hashable | Expr
    func: Callable
    token: int
    cond_attach: ExprAttach
    help: list | None

    def __hash__(self):
        return object.__hash__(self)


current_module = ContextVar("aha_module")
cugp = ContextVar("aha_use_global_prefix", default=False)
current_event: ContextVar[BaseEvent] = ContextVar("aha_event", default=None)
current_match: ContextVar[Match] = ContextVar("aha_match", default=None)  # PM.pattern
current_args: ContextVar[Sequence[str | MsgSeg]] = ContextVar("aha_args", default=None)  # PM.command
current_lang = ContextVar("aha_lang", default=cfg.lang)

start_handlers: list[Callable] = []
clean_handlers: list[Callable] = []
help_items: dict[str, tuple[Expr, str | None]] = {}

_message_handlers = DefaultIndexedDict(ExprPool[Expr, Callable[[MessageChain], MessageChain]])
_notice_handlers = DefaultIndexedDict(ExprPool[Expr, None])
_request_handlers = DefaultIndexedDict(ExprPool[Expr, None])
_meta_handlers = DefaultIndexedDict(ExprPool[Expr, None])
_external_handlers = DefaultIndexedDict(ExprPool[Expr, None])

# region Decorators
# 装饰器参数的基础默认值
_MESSAGE_DEFAULTS = {"exp": None, "threadable": True, "debug": False, "pre_hook": None, "register_help": None}
_COMMON_DEFAULTS = {"exp": None, "threadable": True, "debug": False}
_EXTERNAL_DEFAULTS = {"threadable": True}


def _resolve_params(params: dict, class_params, defaults: dict):
    """构建装饰器参数"""
    inherit = params["inherit"]
    resolved = {}
    for key, default in defaults.items():
        if (value := params[key]) is _unset and inherit and class_params:
            value = class_params[key]
        if value is _unset:
            value = default
        resolved[key] = value
    for key, value in params.items():
        if key in resolved or key == "inherit":
            continue
        if value is not _unset:
            resolved[key] = value
    return resolved


def _add_handler(handlers: DefaultIndexedDict[Any, ExprPool], func, cond_attach, args, key, help=None):
    pool = handlers[args := frozenset(args)]
    func_meta = CallbackMeta(args, pool, key, func, pool.add(key, func, cond_attach), cond_attach, help)
    if (metas := getattr(target := get_true_func(func), "__Aha__meta", None)) is None:
        metas = set()
        target.__Aha__meta = metas
    metas.add(func_meta)
    return func_meta


def _register_message(func, conditions, params: dict[str, Any | dict]):
    module = module[1] if (module := FULL_AHA_MODULE_PATTERN.match(func.__module__)) else caller_aha_module()
    current_module.set(module)

    conditions = build_cond(conditions, EventCategory.CHAT, params["exp"], params["debug"])
    # 通过 event 关键字参数的类型注解添加 ValidateBy 条件
    if not field_exists(conditions, (PM.msg, PM.command, PM.msg_chain)):
        if (
            (ann := get_type_hints(get_true_func(func)).get("event"))
            and (ann := getattr(ann, "__pydantic_generic_metadata__", None))
            and (ann := ann.get("args"))
        ):
            (conditions := And(conditions, PM.msg_chain.validateby(TypeAdapter(MessageChain[ann[0]]))))._exp = params["exp"]
        if cfg.debug:
            conditions._debug = params["debug"]

    added = None
    if register_help := params["register_help"]:
        help_expr = conditions.modify(
            PM.command == None, PM.limit == None, PM.message == None, PM.message_chain == None, PM.prefix == None
        )
        added = []
        for k, v in register_help.items():
            help_items[k] = (help_expr, v)
            added.append(k)

    (args := [s for s in get_arg_names(func) if s in _message_args]).sort()
    return _add_handler(
        _message_handlers,
        func,
        ExprAttach(
            module,
            params["threadable"],
            binary_expr_exists(conditions, (Apply, GetAttr, Call)),
            params["pre_hook"],
            register_help is not None,
        ),
        args,
        conditions,
        added,
    )


def _register_common(handlers, event_category, func, conditions, params):
    module = module[1] if (module := FULL_AHA_MODULE_PATTERN.match(func.__module__)) else caller_aha_module()
    current_module.set(module)
    conditions = build_cond(conditions, event_category, params["exp"], params["debug"])
    (args := [s for s in get_arg_names(func) if s in _other_args]).sort()
    return _add_handler(
        handlers,
        func,
        ExprAttach(module, params["threadable"], binary_expr_exists(conditions, (Apply, GetAttr, Call))),
        args,
        conditions,
    )


def _register_external(func, params: dict):
    module = module[1] if (module := FULL_AHA_MODULE_PATTERN.match(func.__module__)) else caller_aha_module()
    current_module.set(module)
    (args := [s for s in get_arg_names(func) if s in _external_args]).sort()
    return _add_handler(_external_handlers, func, ExprAttach(module, params.pop("threadable")), args, **params)


def _register_class(kind, cls: type, defaults):
    for name, attr in list(cls.__dict__.items()):
        if not (pending := getattr(raw := get_true_func(attr), "__Aha__pending", None)):
            continue

        if (self_ := getattr(cls, name, None)) and (self_ := getattr(self_, "__self__", None)) is not None:
            owner = self_ if isinstance(self_, type) else type(self_)
        else:
            owner = cls
        class_meta = getattr(owner, "__Aha__class_meta", None)
        if not (rec := next((r for r in class_meta if r[0] is kind), None) if class_meta else None):
            continue
        _, class_conditions, class_params = rec

        for i in range(len(pending) - 1, -1, -1):
            if pending[i][0] is not kind:
                continue

            _, conditions, pparams, initial_meta = pending[i]
            # 移除已注册的方法自身条件项
            initial_meta.pool.remove(initial_meta.token)
            if metas := getattr(raw, "__Aha__meta", None):
                metas.discard(initial_meta)
            if initial_meta.help:
                for k in initial_meta.help:
                    help_items.pop(k, None)
            if pparams["inherit"]:
                conditions.extendleft(reversed(class_conditions))
            params = _resolve_params(pparams, class_params, defaults)

            if isinstance(attr, staticmethod):
                target = raw
            elif isinstance(attr, classmethod):
                target = raw.__get__(cls)
            else:
                raise TypeError(_("dispatcher.class.instance_method"))

            match kind:
                case EventCategory.CHAT:
                    _register_message(target, conditions, params)
                case EventCategory.NOTICE:
                    _register_common(_notice_handlers, EventCategory.NOTICE, target, conditions, params)
                case EventCategory.REQUEST:
                    _register_common(_request_handlers, EventCategory.REQUEST, target, conditions, params)
                case EventCategory.META:
                    _register_common(_meta_handlers, EventCategory.META, target, conditions, params)
                case EventCategory.EXTERNAL:
                    _register_external(target, params)

            del pending[i]
        if not pending:
            delattr(raw, "__Aha__pending")


_noneable = {_unset, None}


def _make_decorator(in_class, kind: EventCategory, conditions, params: dict, defaults, register_func):
    def decorator(obj):
        if isinstance(obj, type):
            # 类装饰
            if params.get("register_help", _unset) not in _noneable:
                raise TypeError(_("dispatcher.class.register_help") % {"class": obj.__name__})
            if (metas := getattr(obj, "__Aha__class_meta", None)) is None:
                type.__setattr__(obj, "__Aha__class_meta", metas := [])
            elif any(meta[0] is kind for meta in metas):
                _logger.warning(_("dispatcher.class.duplicate") % {"class": obj.__name__, "kind": kind.value})
            metas.append((kind, conditions, params))
            _register_class(kind, obj, defaults)
            return obj
        if in_class:
            # 类体内方法
            if (pending := getattr(target := get_true_func(obj), "__Aha__pending", None)) is None:
                target.__Aha__pending = pending = []
            pending.append((kind, deque(conditions), params, register_func(target)))
            return obj
        register_func(obj)
        return obj

    return decorator


_message_args = {"event", "match_", "args", "localizer"}


if TYPE_CHECKING:

    @overload
    def on_message[T: type](
        *conditions: Expr | str | Pattern | Sequence[str | type[MsgSeg]],
        exp: float = None,
        threadable: bool = True,
        debug: bool = False,
        pre_hook: Callable[[MessageChain], MessageChain] = None,
    ) -> Callable[[T], T]: ...

    @overload
    def on_message[T: Callable](
        *conditions: Expr | str | Pattern | Sequence[str | type[MsgSeg]],
        exp: float = None,
        threadable: bool = True,
        debug=False,
        pre_hook: Callable[[MessageChain], MessageChain] = None,
        register_help: dict[str, str | None] = None,
        inherit: bool = True,
    ) -> Callable[[T], T]: ...

    @overload
    def on_message[T: Callable](
        *conditions: Expr | str | Pattern | Sequence[str | type[MsgSeg]],
        callback: T,
        exp: float = None,
        threadable: bool = True,
        debug=False,
        pre_hook: Callable[[MessageChain], MessageChain] = None,
        register_help: dict[str, str | None] = None,
        inherit: bool = True,
    ) -> T: ...


def on_message(
    *conditions, exp=_unset, threadable=_unset, debug=_unset, pre_hook=_unset, callback=None, register_help=_unset, inherit=True
):
    """`Message` 事件回调函数装饰器
    - 被装饰的函数必须是异步协程（`async def`），可以选择性声明以下关键字参数：
      - `event`: `models.api.Message`对象。
      - `match_`: 若表达式中采用了 `PM.pattern`（包括使用了默认字符串）则传递 `re.Match` 对象，否则为None。
      - `args`: 若表达式中采用了 `PM.command`（包括使用了默认序列）则传递包含了参数的列表，否则为None。
      - `localizer`: Callable[[str], str] 本地化方法。

    - 不得装饰非 Aha 模块的函数。

    - 本地化方法：
      - 若表达式的 `PM.pattern` 或 `PM.message` 与 `core.i18n._` 方法的返回值进行 `Equal`(`==`) 运算，
      - 本地化方法将返回本地化键名在匹配到的消息对应的语言下的翻译结果；
      - 否则会返回 bot 声明的语言或默认语言下的翻译结果。

    - 可用于装饰类：类中所有使用相同装饰器的方法会自动继承类装饰器声明的 `exp`/`threadable`/`debug`/`pre_hook`。
      类条件与方法条件为并列关系，装饰类时不进行 `build_cond` 等操作，仅在装饰方法时统一执行。
      方法可声明 `inherit=False` 以忽略类装饰器的默认参数，改用框架默认值。
      类装饰器工厂不支持声明 `register_help`，请在方法上声明。

    非线程安全。

    Args:
        exp: 该表达式实例将在几秒钟后/何时销毁，声明此即视为该回调一次性。若传入的值小于10^9，将会被 `build_cond` 修正为与当前秒级时间戳累加。
        debug: 若 `cfg.debug` 为 `True` ，评估该表达式后会打印整个表达式中所有参与评估的二元表达式的两个操作数和匹配结果。
        pre_hook: 对消息链进行预处理，返回值将作用于表达式评估和回调传参。
        register_help: 将 `key` 注册进 Aha 维护的菜单词条字典，如果 `value` 有值，则将其作为说明。仅支持在方法（函数）上声明，不得用于类装饰器工厂。
        inherit: 为 `False` 时忽略类装饰器声明的默认参数。
    """

    params = dict(exp=exp, threadable=threadable, debug=debug, pre_hook=pre_hook, register_help=register_help, inherit=inherit)
    decorator = _make_decorator(
        "__module__" in _getframe(1).f_locals,
        EventCategory.CHAT,
        conditions,
        params,
        _MESSAGE_DEFAULTS,
        lambda obj: _register_message(obj, conditions, _resolve_params(params, None, _MESSAGE_DEFAULTS)),
    )
    return decorator(callback) if callback else decorator


_other_args = {"event", "localizer"}


if TYPE_CHECKING:

    @overload
    def on_notice[T: type](
        *conditions: Expr | str, exp: float = None, threadable: bool = True, debug: bool = False
    ) -> Callable[[T], T]: ...

    @overload
    def on_notice[T: Callable](
        *conditions: Expr | str, exp: float = None, threadable: bool = True, debug=False, inherit: bool = True
    ) -> Callable[[T], T]: ...

    @overload
    def on_notice[T: Callable](
        *conditions: Expr | str, callback: T, exp: float = None, threadable: bool = True, debug=False, inherit: bool = True
    ) -> T: ...


def on_notice(*conditions, exp=_unset, threadable=_unset, debug=_unset, callback=None, inherit=True):
    """`Notice` 事件回调函数装饰器
    - 被装饰的函数必须是异步协程（`async def`），可以选择性声明以下关键字参数：
      - `event`: `models.api.Notice`对象。
      - `localizer`: Callable[[str], str] 本地化方法，返回 bot 声明的语言或默认语言下的翻译结果。

    - 不得装饰非 Python 实现的函数，因为无法获取参数信息。

    - 可用于装饰类：类中所有使用相同装饰器的方法会自动继承类装饰器声明的 `exp`/`threadable`/`debug`，
      类条件与方法条件为并列关系。方法可声明 `inherit=False` 以忽略类装饰器的默认参数。

    非线程安全。

    Args:
        exp: 该表达式实例将在几秒钟后/何时销毁，一般用于一次性表达式。若传入的值小于10^9，将会被 `build_cond` 修正为与当前秒级时间戳累加。
        debug: 若 `cfg.debug` 为 `True` ，评估该表达式后会打印整个表达式中所有参与评估的二元表达式的两个操作数和匹配结果。
        inherit: 为 `False` 时忽略类装饰器声明的默认参数。
    """

    params = dict(exp=exp, threadable=threadable, debug=debug, inherit=inherit)
    decorator = _make_decorator(
        "__module__" in _getframe(1).f_locals,
        EventCategory.NOTICE,
        conditions,
        params,
        _COMMON_DEFAULTS,
        lambda obj: _register_common(
            _notice_handlers, EventCategory.NOTICE, obj, conditions, _resolve_params(params, None, _COMMON_DEFAULTS)
        ),
    )
    return decorator(callback) if callback else decorator


if TYPE_CHECKING:

    @overload
    def on_request[T: type](
        *conditions: Expr | str, exp: float = None, threadable: bool = True, debug: bool = False
    ) -> Callable[[T], T]: ...

    @overload
    def on_request[T: Callable](
        *conditions: Expr | str, exp: float = None, threadable: bool = True, debug=False, inherit: bool = True
    ) -> Callable[[T], T]: ...

    @overload
    def on_request[T: Callable](
        *conditions: Expr | str, callback: T, exp: float = None, threadable: bool = True, debug=False, inherit: bool = True
    ) -> T: ...


def on_request(*conditions, exp=_unset, threadable=_unset, debug=_unset, callback=None, inherit=True):
    """`Request` 事件回调函数装饰器
    - 被装饰的函数必须是异步协程（`async def`），可以选择性声明以下关键字参数：
      - `event`: `models.api.Request`对象。
      - `localizer`: Callable[[str], str] 本地化方法，返回 bot 声明的语言或默认语言下的翻译结果。

    - 不得装饰非 Python 实现的函数，因为无法获取参数信息。

    - 可用于装饰类：类中所有使用相同装饰器的方法会自动继承类装饰器声明的 `exp`/`threadable`/`debug`，
      类条件与方法条件为并列关系。方法可声明 `inherit=False` 以忽略类装饰器的默认参数。

    非线程安全。

    Args:
        exp: 该表达式实例将在几秒钟后/何时销毁，一般用于一次性表达式。若传入的值小于10^9，将会被 `build_cond` 修正为与当前秒级时间戳累加。
        debug: 若 `cfg.debug` 为 `True` ，评估该表达式后会打印整个表达式中所有参与评估的二元表达式的两个操作数和匹配结果。
        inherit: 为 `False` 时忽略类装饰器声明的默认参数。
    """

    params = dict(exp=exp, threadable=threadable, debug=debug, inherit=inherit)
    decorator = _make_decorator(
        "__module__" in _getframe(1).f_locals,
        EventCategory.REQUEST,
        conditions,
        params,
        _COMMON_DEFAULTS,
        lambda obj: _register_common(
            _request_handlers, EventCategory.REQUEST, obj, conditions, _resolve_params(params, None, _COMMON_DEFAULTS)
        ),
    )
    return decorator(callback) if callback else decorator


if TYPE_CHECKING:

    @overload
    def on_meta[T: type](
        *conditions: Expr | str, exp: float = None, threadable: bool = True, debug: bool = False
    ) -> Callable[[T], T]: ...

    @overload
    def on_meta[T: Callable](
        *conditions: Expr | str, exp: float = None, threadable: bool = True, debug=False, inherit: bool = True
    ) -> Callable[[T], T]: ...

    @overload
    def on_meta[T: Callable](
        *conditions: Expr | str, callback: T, exp: float = None, threadable: bool = True, debug=False, inherit: bool = True
    ) -> T: ...


def on_meta(*conditions, exp=_unset, threadable=_unset, debug=_unset, callback=None, inherit=True):
    """`MetaEvent` 事件回调函数装饰器
    - 被装饰的函数必须是异步协程（`async def`），可以选择性声明以下关键字参数：
      - `event`: `models.api.MetaEvent`对象。
      - `localizer`: Callable[[str], str] 本地化方法，返回 bot 声明的语言或默认语言下的翻译结果。

    - 不得装饰非 Python 实现的函数，因为无法获取参数信息。

    - 可用于装饰类：类中所有使用相同装饰器的方法会自动继承类装饰器声明的 `exp`/`threadable`/`debug`，
      类条件与方法条件为并列关系。方法可声明 `inherit=False` 以忽略类装饰器的默认参数。

    非线程安全。

    Args:
        exp: 该表达式实例将在几秒钟后/何时销毁，一般用于一次性表达式。若传入的值小于10^9，将会被 `build_cond` 修正为与当前秒级时间戳累加。
        debug: 若 `cfg.debug` 为 `True` ，评估该表达式后会打印整个表达式中所有参与评估的二元表达式的两个操作数和匹配结果。
        pre_hook: 对消息链进行预处理，返回值将作用于表达式评估和回调传参。
        inherit: 为 `False` 时忽略类装饰器声明的默认参数。
    """

    params = dict(exp=exp, threadable=threadable, debug=debug, inherit=inherit)
    decorator = _make_decorator(
        "__module__" in _getframe(1).f_locals,
        EventCategory.META,
        conditions,
        params,
        _COMMON_DEFAULTS,
        lambda obj: _register_common(
            _meta_handlers, EventCategory.META, obj, conditions, _resolve_params(params, None, _COMMON_DEFAULTS)
        ),
    )
    return decorator(callback) if callback else decorator


_external_args = _other_args | {"data"}


if TYPE_CHECKING:

    @overload
    def on_external[T: type](key: Any = _unset, *, threadable: bool = True) -> Callable[[T], T]: ...

    @overload
    def on_external[T: Callable](key, threadable=True, inherit: bool = True) -> Callable[[T], T]: ...

    @overload
    def on_external[T: Callable](key, threadable=True, inherit: bool = True, *, callback: T) -> T: ...


def on_external(key=_unset, threadable=_unset, callback=None, inherit=True):
    """其他服务请求回调函数装饰器
    - 被装饰的函数必须是异步协程（`async def`），可以选择性声明以下关键字参数：
      - `data`: 由 API 层上报的数据。
      - `localizer`: Callable[[str], str] 本地化方法，返回 API 层上报时指定的语言下的翻译结果。

    - 不得装饰非 Python 实现的函数，因为无法获取参数信息。

    - 可用于装饰类：类中所有使用相同装饰器的方法会自动继承类装饰器声明的 `threadable`。方法可声明 `inherit=False` 以忽略类装饰器继承的默认参数。

    非线程安全。

    Args:
        key: 区分调用函数的特征id。
        inherit: 为 `False` 时忽略类装饰器声明的默认参数。
    """

    params = dict(key=key, threadable=threadable, inherit=inherit)
    decorator = _make_decorator(
        "__module__" in _getframe(1).f_locals,
        EventCategory.EXTERNAL,
        (),
        params,
        _EXTERNAL_DEFAULTS,
        lambda obj: _register_external(obj, _resolve_params(params, None, _EXTERNAL_DEFAULTS)),
    )
    return decorator(callback) if callback else decorator


def on_start(func: Callable = None):
    """用于模块注册 Aha 启动时或模块重载时执行的函数。非线程安全。"""
    if func is None:
        return on_start
    start_handlers.append(func)
    return func


def on_cleanup(func: Callable = None):
    """用于模块注册 Aha 正常关闭时或模块重载前卸载时执行的函数。非线程安全。"""
    if func is None:
        return on_cleanup
    clean_handlers.append(func)
    return func


# endregion
# region event processers
_waiting_event_calls = 0  # all_ready 永远不会再被 clear，所以该变量只增不减。


def _processer[T](func: T = None) -> T:
    @wraps(func)
    async def wrapper(
        event: BaseEvent,
        *args,
        __func=ThreadSafeAsyncMeta.decorator(func) if cfg.execution_mode == "thread" else func,
        **kwargs,
    ):
        global _waiting_event_calls
        from .api_service import MAX_WAITING_TASKS, bots

        if event.bot_id is not None:
            if not (bot := bots[event.bot_id]) or bot.block_event:
                return
            current_lang.set(bot.config.get("lang", None))

        if not status.all_ready.is_set():
            if _waiting_event_calls > MAX_WAITING_TASKS:
                raise MemoryError(_("router.many_wating"))
            _waiting_event_calls += 1
            await status.all_ready

        current_event.set(event)
        return await __func(event, *args, **kwargs)

    return wrapper


if cfg.execution_mode == "thread":

    async def _into_thread(func, threadable, *args):
        if threadable:
            await status.async_loop_executor.submit(func, *args)
        else:
            create_task(func(*args), eager_start=True)

else:

    async def _into_thread(func, _, *args):
        create_task(func(*args), eager_start=True)


async def _message_evaluate(event: Message, expr, func, token, attach: ExprAttach, pool, e, m, a, l):
    copied = False
    if attach.need_isolation:
        cprms.set(None)
        cprmc.set(None)
        current_event.set(event := event.model_copy(deep=True))
        copied = True
        if attach.pre_hook:
            event.message = await async_run_func(attach.pre_hook, event.message)
    if attach.use_global_prefix:
        cugp.set(True)

    if await evaluate(event, expr, token, pool):
        kwargs = {}
        if e:
            if not copied:
                event = event.model_copy(deep=True)
            event.message = remove_msg_seq_prefix(event.message) if (cache := cprmc.get()) is None else cache
            kwargs["event"] = event
        if m:
            kwargs["match_"] = current_match.get()
        if a:
            kwargs["args"] = current_args.get()
        if l:
            kwargs["localizer"] = create_translator(attach.aha_module, current_lang.get())
        await func(**kwargs)


@_processer
async def process_message(event: Message, ignore_prefix=False, once: CallbackMeta = None):
    # 删除过时缓存
    cprmc.set(None)
    cprms.set(None)

    if once:
        k, pool, expr, func, token, attach = once.args, once.pool, once.condition, once.func, once.token, once.cond_attach
        e, m, a, l = "event" in k, "match_" in k, "args" in k, "localizer" in k
        current_module.set(attach.aha_module)
        if ignore_prefix:
            expr = expr.modify(PM.prefix == False)
        await _into_thread(_message_evaluate, attach.threadable, event, expr, func, token, attach, pool, e, m, a, l)
    else:
        for k, pool in _message_handlers.safe_iter_items():
            e, m, a, l = "event" in k, "match_" in k, "args" in k, "localizer" in k
            for expr, func, token, attach in pool:
                current_module.set(attach.aha_module)
                if ignore_prefix:
                    expr = expr.modify(PM.prefix == False)
                await _into_thread(_message_evaluate, attach.threadable, event, expr, func, token, attach, pool, e, m, a, l)


async def _notice_evaluate(event: Notice, expr, func, token, attach: ExprAttach, pool, e, l):
    current_module.set(attach.aha_module)
    if attach.need_isolation:
        event = event.model_copy(deep=True)
    if await evaluate(event, expr, token, pool):
        kwargs = {}
        if e:
            kwargs["event"] = event if attach.need_isolation else event.model_copy(deep=True)
        if l:
            kwargs["localizer"] = create_translator(attach.aha_module, current_lang.get())
        await func(**kwargs)


@_processer
async def process_notice(event: Notice, once: CallbackMeta = None):
    if once:
        k, pool, expr, func, token, attach = once.args, once.pool, once.condition, once.func, once.token, once.cond_attach
        e, l = "event" in k, "localizer" in k
        await _into_thread(_notice_evaluate, attach.threadable, event, expr, func, token, attach, pool, e, l)
    else:
        for k, pool in _notice_handlers.safe_iter_items():
            e, l = "event" in k, "localizer" in k
            for expr, func, token, attach in pool:
                await _into_thread(_notice_evaluate, attach.threadable, event, expr, func, token, attach, pool, e, l)


async def _request_evaluate(event: Request, expr, func, token, attach: ExprAttach, pool, e, l):
    current_module.set(attach.aha_module)
    if attach.need_isolation:
        event = event.model_copy(deep=True)
    if await evaluate(event, expr, token, pool):
        kwargs = {}
        if e:
            kwargs["event"] = event if attach.need_isolation else event.model_copy(deep=True)
        if l:
            kwargs["localizer"] = create_translator(attach.aha_module, current_lang.get())
        await func(**kwargs)


@_processer
async def process_request(event: Request, once: CallbackMeta = None):
    if once:
        k, pool, expr, func, token, attach = once.args, once.pool, once.condition, once.func, once.token, once.cond_attach
        e, l = "event" in k, "localizer" in k
        await _into_thread(_request_evaluate, attach.threadable, event, expr, func, token, attach, pool, e, l)
    else:
        for k, pool in _request_handlers.safe_iter_items():
            e, l = "event" in k, "localizer" in k
            for expr, func, token, attach in pool:
                await _into_thread(_request_evaluate, attach.threadable, event, expr, func, token, attach, pool, e, l)


async def _meta_evaluate(event: MetaEvent, expr, func, token, attach: ExprAttach, pool, e, l):
    current_module.set(attach.aha_module)
    if attach.need_isolation:
        event = event.model_copy(deep=True)
    if await evaluate(event, expr, token, pool):
        kwargs = {}
        if e:
            kwargs["event"] = event if attach.need_isolation else event.model_copy(deep=True)
        if l:
            kwargs["localizer"] = create_translator(attach.aha_module, current_lang.get())
        await func(**kwargs)


@_processer
async def process_meta(event: MetaEvent, once: CallbackMeta = None):
    if once:
        k, pool, expr, func, token, attach = once.args, once.pool, once.condition, once.func, once.token, once.cond_attach
        e, l = "event" in k, "localizer" in k
        await _into_thread(_meta_evaluate, attach.threadable, event, expr, func, token, attach, pool, e, l)
    else:
        for k, pool in _meta_handlers.safe_iter_items():
            e, l = "event" in k, "localizer" in k
            for expr, func, token, attach in pool:
                await _into_thread(_meta_evaluate, attach.threadable, event, expr, func, token, attach, pool, e, l)


async def _external_evaluate(event: External, key, func, attach: ExprAttach, e, d, l):
    # current_module.set(attach.aha_module)
    if key == event.key:
        kwargs = {}
        if e:
            kwargs["event"] = copied_event = event.model_copy(deep=True)
            if d:
                kwargs["data"] = copied_event.data
        elif d:
            kwargs["data"] = deepcopy(event.data)
        if l:
            kwargs["localizer"] = create_translator(attach.aha_module, event.lang or current_lang.get())
        await func(**kwargs)


@_processer
async def process_external(event: External, once: CallbackMeta = None):
    if once:
        args, pool, key, func, attach = once.args, once.pool, once.condition, once.func, once.cond_attach
        e, d, l = "event" in args, "data" in args, "localizer" in args
        await _into_thread(_external_evaluate, attach.threadable, event, key, func, attach, e, d, l)
    else:
        for args, pool in _external_handlers.safe_iter_items():
            e, d, l = "event" in args, "data" in args, "localizer" in args
            for key, func, _, attach in pool:
                await _into_thread(_external_evaluate, attach.threadable, event, key, func, attach, e, d, l)


async def process_start():
    logger = getLogger("AHA (start callback)")
    for t in start_handlers:
        try:
            await async_run_func(t)
        except Exception as e:
            logger.exception(e)
    start_handlers.clear()


async def process_clean():
    logger = getLogger("AHA (clean callback)")
    for t in clean_handlers:
        try:
            await async_run_func(t)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            logger.exception(e)
    clean_handlers.clear()


# endregion
def clear_handlers():
    for h in _message_handlers.values():
        h.clear()
    for h in _notice_handlers.values():
        h.clear()
    for h in _request_handlers.values():
        h.clear()
    for h in _meta_handlers.values():
        h.clear()
    for h in _external_handlers.values():
        h.clear()
    start_handlers.clear()
    clean_handlers.clear()
    help_items.clear()
