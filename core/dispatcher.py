from asyncio import create_task
from collections import defaultdict
from collections.abc import Callable, Container, Hashable, Sequence
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from functools import wraps
from logging import getLogger
from re import Match, Pattern
from typing import TYPE_CHECKING, get_type_hints, overload

from pydantic import TypeAdapter

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
        self._key_nodes: defaultdict[Key, list[ExprPoolNode[Key]]] = defaultdict(list)

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
        self._key_nodes[key].append(node)
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
        (nodes := self._key_nodes[node.key]).remove(node)
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

    def __hash__(self):
        return object.__hash__(self)


current_module = ContextVar("aha_module")
cugp = ContextVar("aha_use_global_prefix", default=False)
current_event: ContextVar[BaseEvent] = ContextVar("aha_event", default=None)
current_match: ContextVar[Match] = ContextVar("aha_match", default=None)  # PM.pattern
current_args: ContextVar[list[str | MsgSeg]] = ContextVar("aha_args", default=None)  # PM.command
current_lang = ContextVar("aha_lang", default=cfg.lang)

start_handlers: list[Callable] = []
clean_handlers: list[Callable] = []
help_items: list[tuple[str, Expr, str | None]] = []

_message_handlers = DefaultIndexedDict(ExprPool[Expr, Callable[[MessageChain], MessageChain]])
_notice_handlers = DefaultIndexedDict(ExprPool[Expr, None])
_request_handlers = DefaultIndexedDict(ExprPool[Expr, None])
_meta_handlers = DefaultIndexedDict(ExprPool[Expr, None])
_external_handlers = DefaultIndexedDict(ExprPool[Expr, None])

# region Decorators
_message_args = {"event", "match_", "args", "localizer"}


if TYPE_CHECKING:

    @overload
    def on_message[T: Callable](
        *conditions: Expr | str | Pattern | Sequence[str | type[MsgSeg]],
        exp: float = None,
        debug=False,
        pre_hook: Callable[[MessageChain], MessageChain] = None,
        register_help: dict[str, str | None] = None,
    ) -> Callable[[T], T]: ...

    @overload
    def on_message[T: Callable](
        *conditions: Expr | str | Pattern | Sequence[str | type[MsgSeg]],
        callback: T,
        exp: float = None,
        debug=False,
        pre_hook: Callable[[MessageChain], MessageChain] = None,
        register_help: dict[str, str | None] = None,
    ) -> T: ...


def on_message(*conditions, exp=None, threadable=True, debug=False, pre_hook=None, callback=None, register_help: dict = None):
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

    非线程安全。

    Args:
        exp: 该表达式实例将在几秒钟后/何时销毁，声明此即视为该回调一次性。若传入的值小于10^9，将会被 `build_cond` 修正为与当前秒级时间戳累加。
        debug: 若 `cfg.debug` 为 `True` ，评估该表达式后会打印整个表达式中所有参与评估的二元表达式的两个操作数和匹配结果。
        pre_hook: 对消息链进行预处理，返回值将作用于表达式评估和回调传参。
        register_help: 将 `key` 注册进 Aha 维护的菜单词条列表，如果 `value` 有值，则将其作为说明。
    """

    def decorator(func: Callable):
        nonlocal conditions
        if module := FULL_AHA_MODULE_PATTERN.match(func.__module__):
            module = module[1]
        else:
            module = caller_aha_module()
        current_module.set(module)

        conditions = build_cond(conditions, EventCategory.CHAT, exp, debug)
        # 通过 event 关键字参数的类型注解添加 ValidateBy 条件
        if not field_exists(conditions, (PM.msg, PM.command, PM.msg_chain)):
            if (
                (ann := get_type_hints(get_true_func(func)).get("event"))
                and (ann := getattr(ann, "__pydantic_generic_metadata__", None))
                and (ann := ann.get("args"))
            ):
                (conditions := And(conditions, PM.msg_chain.validateby(TypeAdapter(MessageChain[ann[0]]))))._exp = exp
            conditions = conditions.modify(PM.limit == None)
            if cfg.debug:
                conditions._debug = debug

        # 注册菜单
        if register_help:
            help_expr = conditions.modify(
                PM.command == None,
                PM.limit == None,
                PM.message == None,
                PM.message_chain == None,
                PM.prefix == None,
            )
            for k, v in register_help.items():
                help_items.append((k, help_expr, v))

        (args := [s for s in get_arg_names(func) if s in _message_args]).sort()

        cond_attach = ExprAttach(
            module, threadable, binary_expr_exists(conditions, (Apply, GetAttr, Call)), pre_hook, register_help is not None
        )
        token = _message_handlers[args := frozenset(args)].add(conditions, func, cond_attach)

        func_meta = CallbackMeta(args, _message_handlers[args], conditions, func, token, cond_attach)
        if metas := getattr(func, "aha_meta", None):
            metas.append(func_meta)
        else:
            func.aha_meta = [func_meta]

        return func

    return decorator(callback) if callback else decorator


_other_args = {"event", "localizer"}


if TYPE_CHECKING:

    @overload
    def on_notice[T: Callable](*conditions: Expr | str, exp: float = None, debug=False) -> Callable[[T], T]: ...

    @overload
    def on_notice[T: Callable](*conditions: Expr | str, callback: T, exp: float = None, debug=False) -> T: ...


def on_notice(*conditions, exp=None, threadable=True, debug=False, callback=None):
    """`Notice` 事件回调函数装饰器
    - 被装饰的函数必须是异步协程（`async def`），可以选择性声明以下关键字参数：
      - `event`: `models.api.Notice`对象。
      - `localizer`: Callable[[str], str] 本地化方法，返回 bot 声明的语言或默认语言下的翻译结果。

    - 不得装饰非 Python 实现的函数，因为无法获取参数信息。

    非线程安全。

    Args:
        exp: 该表达式实例将在几秒钟后/何时销毁，一般用于一次性表达式。若传入的值小于10^9，将会被 `build_cond` 修正为与当前秒级时间戳累加。
        debug: 若 `cfg.debug` 为 `True` ，评估该表达式后会打印整个表达式中所有参与评估的二元表达式的两个操作数和匹配结果。
    """

    def decorator(func: Callable):
        nonlocal conditions
        if module := FULL_AHA_MODULE_PATTERN.match(func.__module__):
            module = module[1]
        else:
            module = caller_aha_module()
        current_module.set(module)
        (args := [s for s in get_arg_names(func) if s in _other_args]).sort()

        if not field_exists(conditions := build_cond(conditions, EventCategory.NOTICE, exp, debug), (PM.type_, PM.sub_type)):
            conditions = conditions.modify(PM.limit == None)
            if cfg.debug:
                conditions._debug = debug

        cond_attach = ExprAttach(module, threadable, binary_expr_exists(conditions, (Apply, GetAttr, Call)))
        token = _notice_handlers[args := frozenset(args)].add(conditions, func, cond_attach)

        func_meta = CallbackMeta(args, _notice_handlers[args], conditions, func, token, cond_attach)
        if metas := getattr(func, "aha_meta", None):
            metas.append(func_meta)
        else:
            func.aha_meta = [func_meta]
        return func

    return decorator(callback) if callback else decorator


if TYPE_CHECKING:

    @overload
    def on_request[T: Callable](*conditions: Expr | str, exp: float = None, debug=False) -> Callable[[T], T]: ...

    @overload
    def on_request[T: Callable](*conditions: Expr | str, callback: T, exp: float = None, debug=False) -> T: ...


def on_request(*conditions, exp=None, threadable=True, debug=False, callback=None):
    """`Request` 事件回调函数装饰器
    - 被装饰的函数必须是异步协程（`async def`），可以选择性声明以下关键字参数：
      - `event`: `models.api.Request`对象。
      - `localizer`: Callable[[str], str] 本地化方法，返回 bot 声明的语言或默认语言下的翻译结果。

    - 不得装饰非 Python 实现的函数，因为无法获取参数信息。

    非线程安全。

    Args:
        exp: 该表达式实例将在几秒钟后/何时销毁，一般用于一次性表达式。若传入的值小于10^9，将会被 `build_cond` 修正为与当前秒级时间戳累加。
        debug: 若 `cfg.debug` 为 `True` ，评估该表达式后会打印整个表达式中所有参与评估的二元表达式的两个操作数和匹配结果。
    """

    def decorator(func: Callable):
        nonlocal conditions
        if module := FULL_AHA_MODULE_PATTERN.match(func.__module__):
            module = module[1]
        else:
            module = caller_aha_module()
        current_module.set(module)
        (args := [s for s in get_arg_names(func) if s in _other_args]).sort()

        if not field_exists(conditions := build_cond(conditions, EventCategory.REQUEST, exp, debug), (PM.type_, PM.sub_type)):
            conditions = conditions.modify(PM.limit == None)
            if cfg.debug:
                conditions._debug = debug

        cond_attach = ExprAttach(module, threadable, binary_expr_exists(conditions, (Apply, GetAttr, Call)))
        token = _request_handlers[args := frozenset(args)].add(conditions, func, cond_attach)

        func_meta = CallbackMeta(args, _request_handlers[args], conditions, func, token, cond_attach)
        if metas := getattr(func, "aha_meta", None):
            metas.append(func_meta)
        else:
            func.aha_meta = [func_meta]
        return func

    return decorator(callback) if callback else decorator


if TYPE_CHECKING:

    @overload
    def on_meta[T: Callable](*conditions: Expr | str, exp: float = None, debug=False) -> Callable[[T], T]: ...

    @overload
    def on_meta[T: Callable](*conditions: Expr | str, callback: T, exp: float = None, debug=False) -> T: ...


def on_meta(*conditions, exp=None, threadable=True, debug=False, callback=None):
    """`MetaEvent` 事件回调函数装饰器
    - 被装饰的函数必须是异步协程（`async def`），可以选择性声明以下关键字参数：
      - `event`: `models.api.MetaEvent`对象。
      - `localizer`: Callable[[str], str] 本地化方法，返回 bot 声明的语言或默认语言下的翻译结果。

    - 不得装饰非 Python 实现的函数，因为无法获取参数信息。

    非线程安全。

    Args:
        exp: 该表达式实例将在几秒钟后/何时销毁，一般用于一次性表达式。若传入的值小于10^9，将会被 `build_cond` 修正为与当前秒级时间戳累加。
        debug: 若 `cfg.debug` 为 `True` ，评估该表达式后会打印整个表达式中所有参与评估的二元表达式的两个操作数和匹配结果。
        pre_hook: 对消息链进行预处理，返回值将作用于表达式评估和回调传参。
    """

    def decorator(func: Callable):
        if module := FULL_AHA_MODULE_PATTERN.match(func.__module__):
            module = module[1]
        else:
            module = caller_aha_module()
        current_module.set(module)
        (args := [s for s in get_arg_names(func) if s in _other_args]).sort()
        cond_attach = ExprAttach(module, threadable, binary_expr_exists(conditions, (Apply, GetAttr, Call)))
        token = _meta_handlers[args := frozenset(args)].add(
            build_cond(conditions, EventCategory.META, exp, debug), func, cond_attach
        )

        func_meta = CallbackMeta(args, _meta_handlers[args], conditions, func, token, cond_attach)
        if metas := getattr(func, "aha_meta", None):
            metas.append(func_meta)
        else:
            func.aha_meta = [func_meta]
        return func

    return decorator(callback) if callback else decorator


_external_args = _other_args | {"data"}


if TYPE_CHECKING:

    @overload
    def on_external[T: Callable](key, threadable=True, *, callback: T) -> T: ...

    @overload
    def on_external[T: Callable](key, threadable=True) -> Callable[[T], T]: ...


def on_external(key, threadable=True, callback=None):
    """其他服务请求回调函数装饰器
    - 被装饰的函数必须是异步协程（`async def`），可以选择性声明以下关键字参数：
      - `data`: 由 API 层上报的数据。
      - `localizer`: Callable[[str], str] 本地化方法，返回 API 层上报时指定的语言下的翻译结果。

    - 不得装饰非 Python 实现的函数，因为无法获取参数信息。

    非线程安全。

    Args:
        key: 区分调用函数的特征id。
    """

    def decorator(func: Callable):
        if module := FULL_AHA_MODULE_PATTERN.match(func.__module__):
            module = module[1]
        else:
            module = caller_aha_module()
        current_module.set(module)
        (args := [s for s in get_arg_names(func) if s in _external_args]).sort()
        token = _external_handlers[args := frozenset(args)].add(key, func, cond_attach := ExprAttach(module, threadable))

        func_meta = CallbackMeta(args, _external_handlers[args], key, func, token, cond_attach)
        if metas := getattr(func, "aha_meta", None):
            metas.append(func_meta)
        else:
            func.aha_meta = [func_meta]
        return func

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
    async def wrapper(event: BaseEvent, *args, __func=ThreadSafeAsyncMeta.decorator(func), **kwargs):
        global _waiting_event_calls
        from .api_service import MAX_WAITING_TASKS, bots

        if bots[event.bot_id].block_event:
            return
        if not status.all_ready.is_set():
            if _waiting_event_calls > MAX_WAITING_TASKS:
                raise MemoryError(_("router.many_wating"))
            _waiting_event_calls += 1
            await status.all_ready

        current_lang.set(next((v.get("lang") for p in cfg.bots for k, v in p.items() if k == event.adapter), None))
        current_event.set(event)
        return await __func(event, *args, **kwargs)

    return wrapper


if cfg.execution_mode == "thread":

    async def _into_thread(func, threadable, *args):
        if threadable:
            await status.async_loop_executor.submit(func, *args)
        else:
            create_task(func(*args))

else:

    async def _into_thread(func, _, *args):
        create_task(func(*args))


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
            event.message = cprmc.get() or remove_msg_seq_prefix(event.message)
            kwargs["event"] = event
        if m:
            kwargs["match_"] = current_match.get()
        if a:
            kwargs["args"] = current_args.get()
        if l:
            kwargs["localizer"] = create_translator(attach.aha_module, current_lang.get())
        create_task(func(**kwargs))


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
        create_task(func(**kwargs))


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
        create_task(func(**kwargs))


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
        create_task(func(**kwargs))


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
        create_task(func(**kwargs))


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
