import re
from abc import abstractmethod
from collections import defaultdict
from collections.abc import Callable, Container, Hashable, Iterable, KeysView, Sequence, ValuesView, MutableSequence
from contextlib import suppress
from contextvars import ContextVar
from functools import partial
from logging import getLogger
from time import localtime, strftime, time
from types import CoroutineType, GenericAlias, UnionType
from typing import TYPE_CHECKING, Any, Hashable, NoReturn, TypedDict, Unpack, _Final, _UnionGenericAlias

from attrs import define, field
from pydantic import TypeAdapter
from pydantic_core._pydantic_core import ValidationError
from sqlalchemy import Column, Float, Integer, String, insert, update

from core.database import db_sessionmaker, dbBase
from core.i18n import LocalizedString
from models.api import (
    BaseEvent,
    EventSubType,
    EventType,
    LifecycleSubType,
    Message,
    MessageEventType,
    MessageSubType,
    MetaEventType,
    NoticeEventType,
    NoticeSubType,
    RequestEventType,
    RequestSubType,
)
from models.core import EventCategory, Group, User
from models.exc import AhaExprFieldDuplicate
from models.msg import At, MsgSeg, MessageChain, Text
from utils.aio import async_all, async_any, async_run_func
from utils.misc import AHA_MODULE_PATTERN, caller_aha_module, find_first_instance, is_prefix, is_suffix
from utils.string import halfwidth

# from models.exc import AhaExprTypeError

from .cache import LRUCache, async_cached, hashkey
from .config import Option, cfg
from .i18n import _
from .identity import group2aha_id, user2aha_id

if TYPE_CHECKING:
    from .dispatcher import ExprPool

__all__ = (
    "Expr",
    "PM",
    "Pmessage",
    "Pmsg",
    "Pmsg_chain",
    "Pcommand",
    "Prequest",
    "Pnotice",
    "Pmeta",
    "Psub_type",
    "Pisgroup",
    "Pisprivate",
    "Pgid",
    "Puid",
    "Pgroup",
    "Puser",
    "Pplatform",
    "Pbot",
    "Pprefix",
    "Padmin",
    "Psuper",
    "Pvalidated",
    "Plimit",
    "In",
    "NotIn",
    "Contains",
    "NotContains",
    "PrefixOf",
    "NotPrefixOf",
    # "SuffixOf",
    # "NotSuffixOf",
    # "SubClassOf",
    # "NotSubClassOf",
    # "SuperClassOf",
    # "NotSuperClassOf",
    # "InstanceOf",
    # "NotInstanceOf",
    # "HasInstance",
    # "NotHasInstance",
    # "SingletonOf",
    # "NotSingletonOf",
    "Match",
    "FullMatch",
    "Search",
    "ValidateBy",
    "ApplyTo",
    "GetAttr",
    "Call",
    "And",
    "Or",
    "Not",
    "and_",
    "or_",
    "not_",
    "Equal",
    "NotEqual",
    "fields",
    "evaluate",
    "modify_expr",
    "field_exists",
    "binary_expr_exists",
    "register_extractor",
)


if DEBUG := cfg.debug:
    _current_debug = ContextVar("aha_debug", default=None)

_logger = getLogger("AHA Expr")


# region 基类/元类
class Expr[Result]:
    """表达式基类"""

    __slots__ = ("_exp",)

    def __init__(self):
        self._exp = None

    def __hash__(self):
        return hash(
            ((self.__class__, self._exp) if self._exp else (self.__class__,))
            + tuple(
                v if isinstance(v, Hashable) else object.__hash__(v)
                for slot in self.__slots__
                if (v := getattr(self, slot, None)) and not slot.startswith("_")
            )
        )

    def modify(self, *overrides: BinaryExpr):
        """递归修改表达式中的指定字段，第二个操作数为 `None` 时删除该字段的表达式"""
        return modify_expr(self, *overrides)

    def has_field(self, field: FieldClause):
        """表达式中是否包含指定字段"""
        return field_exists(self, field)

    @abstractmethod
    async def evaluate(self, msg) -> Result:
        """表达式求值接口

        Returns:
            tuple: 第一个元素为评估结果。第二个元素为由 `Equal` 生成的上下文，第一个元素为正则表达式的 `Match` 对象，第二个元素为语言代码。
        """
        raise NotImplementedError

    # region 运算符
    def __getattr__(self, item):
        return GetAttr(self, item)

    def __and__(self, other):
        return And(self, other)

    def __or__(self, other):
        return Or(self, other)

    def __invert__(self):
        return Not(self)

    def __eq__(self, other):
        return Equal(self, other)

    def __ne__(self, other):
        return NotEqual(self, other)

    def in_(self, other):
        return In(self, other)

    def notin(self, other):
        return NotIn(self, other)

    def contains(self, other):
        return Contains(self, other)

    def notcontains(self, other):
        return NotContains(self, other)

    def prefixof(self, seq):
        # if isinstance(seq, Sequence):
        return PrefixOf(self, seq)

    # raise AhaExprTypeError("prefixof() requires a sequence argument.")

    def notprefixof(self, seq):
        # if isinstance(seq, Sequence):
        return NotPrefixOf(self, seq)

    # raise AhaExprTypeError("notprefixof() requires a sequence argument.")

    def suffixof(self, seq):
        # if isinstance(seq, Sequence):
        return SuffixOf(self, seq)

    # raise AhaExprTypeError("suffixof() requires a sequence argument.")

    def notsuffixof(self, seq):
        # if isinstance(seq, Sequence):
        return NotSuffixOf(self, seq)

    # raise AhaExprTypeError("notsuffixof() requires a sequence argument.")

    """
    def subclassof(self: Expr[type], cls: type | tuple[type, ...]):
        if isinstance(cls, (type, tuple)):
            return SubClassOf(self, cls)
        raise AhaExprTypeError("subclassof() requires a type or tuple argument.")

    def notsubclassof(self: Expr[type], cls: type | tuple[type, ...]):
        if isinstance(cls, (type, tuple)):
            return NotSubClassOf(self, cls)
        raise AhaExprTypeError("notsubclassof() requires a type or tuple argument.")

    def superclassof(self: Expr[type], cls: type):
        if isinstance(cls, type):
            return SuperClassOf(self, cls)
        raise AhaExprTypeError("superclassof() requires a type argument.")

    def notsuperclassof(self: Expr[type], cls: type):
        if isinstance(cls, type):
            return NotSuperClassOf(self, cls)
        raise AhaExprTypeError("notsuperclassof() requires a type argument.")

    def instanceof(self, cls: type | tuple[type, ...]):
        if issubclass(cls, (type, tuple)):
            return InstanceOf(self, cls)
        raise AhaExprTypeError("instanceof() requires a type or tuple argument.")

    def notinstanceof(self, cls: type | tuple[type, ...]):
        if issubclass(cls, (type, tuple)):
            return NotInstanceOf(self, cls)
        raise AhaExprTypeError("notinstanceof() requires a type or tuple argument.")

    def hasinstance(self: Expr[type], obj):
        return HasInstance(self, obj)

    def nothasinstance(self: Expr[type], obj):
        return NotHasInstance(self, obj)
    """

    def singletonof(self, obj):
        """序列是否仅有一个元素且该元素与 `obj` 相等"""
        return SingletonOf(self, obj)

    def notsingletonof(self, obj):
        """序列不只有一个元素或唯一的元素不与 `obj` 相等"""
        return NotSingletonOf(self, obj)

    def match(self, obj):
        """只有 `self` 为 `PM.message` 时，`obj` 才支持为 `Strable`，届时会通过 `re.I` 编译"""
        # if self is PM.message or isinstance(obj, re.Pattern):
        return Match(self, obj)
        # raise AhaExprTypeError(
        #    "match() requires a Strable or Pattern argument when self is PM.message, otherwise only Pattern is supported."
        # )

    def fullmatch(self, obj):
        """只有 `self` 为 `PM.message` 时，`obj` 才支持为 `Strable`，届时会通过 `re.I` 编译"""
        # if self is PM.message or isinstance(obj, re.Pattern):
        return FullMatch(self, obj)
        # raise AhaExprTypeError(
        #    "fullmatch() requires a Strable or Pattern argument when self is PM.message, otherwise only Pattern is supported."
        # )

    def search(self, obj):
        """只有 `self` 为 `PM.message` 时，`obj` 才支持为 `Strable`，届时会通过 `re.I` 编译"""
        # if self is PM.message or isinstance(obj, re.Pattern):
        return Search(self, obj)
        # raise AhaExprTypeError(
        #    "search() requires a Strable or Pattern argument when self is PM.message, otherwise only Pattern is supported."
        # )

    def validateby(self, obj):
        # if isinstance(obj, (type, GenericAlias, UnionType, TypeAdapter, _Final, _UnionGenericAlias)):
        return ValidateBy(self, obj)
        # raise AhaExprTypeError("validateby() requires a type annotation argument.")

    def filter(self, function):
        # if callable(function):
        return ApplyTo(self, partial(filter, function))

    # raise AhaExprTypeError("filter() requires a callable argument.")

    def to_msg_seq(self):
        return ApplyTo(self, MessageChain)

    def applyto(self, callable):
        # if callable(obj):
        return ApplyTo(self, callable)
        # raise AhaExprTypeError("applyto() requires a callable argument.")

    def __lt__(self, *args):
        return GetAttr(self, "__lt__")(*args)

    def __le__(self, *args):
        return GetAttr(self, "__le__")(*args)

    def __gt__(self, *args):
        return GetAttr(self, "__gt__")(*args)

    def __ge__(self, *args):
        return GetAttr(self, "__ge__")(*args)

    def __getitem__(self, *args):
        return GetAttr(self, "__getitem__")(*args)

    def __add__(self, *args):
        return GetAttr(self, "__add__")(*args)

    def __sub__(self, *args):
        return GetAttr(self, "__sub__")(*args)

    def __mul__(self, *args):
        return GetAttr(self, "__mul__")(*args)

    def __matmul__(self, *args):
        return GetAttr(self, "__matmul__")(*args)

    def __truediv__(self, *args):
        return GetAttr(self, "__truediv__")(*args)

    def __floordiv__(self, *args):
        return GetAttr(self, "__floordiv__")(*args)

    def __mod__(self, *args):
        return GetAttr(self, "__mod__")(*args)

    def __pow__(self, *args):
        return GetAttr(self, "__pow__")(*args)

    def __divmod__(self, *args):
        return GetAttr(self, "__divmod__")(*args)

    def __radd__(self, *args):
        return GetAttr(self, "__radd__")(*args)

    def __rsub__(self, *args):
        return GetAttr(self, "__rsub__")(*args)

    def __iadd__(self, *args):
        return GetAttr(self, "__iadd__")(*args)

    def __isub__(self, *args):
        return GetAttr(self, "__isub__")(*args)

    # endregion


if DEBUG and not TYPE_CHECKING:

    class DebugExpr(Expr):
        __slots__ = "_debug"

        def __init__(self):
            self._debug = False
            super().__init__()

    Expr = DebugExpr


class FieldClause[Result](Expr[Result]):
    """字段访问表达式"""

    __slots__ = ("name", "field", "priority")

    def __init__(self, name, field: Field):
        self.name = f"{mod}.{name}" if (mod := caller_aha_module(pattern=AHA_MODULE_PATTERN)) else name
        if self.name in fields:
            raise AhaExprFieldDuplicate(_("expr.fields.409"))

        self.field = field
        self.priority = field.priority
        super().__init__()

        field.clause = self
        fields[self.name] = field
        # 注册具有默认二元表达式的类型
        if field.operand_types:
            for types, operand in field.operand_types.items():
                if isinstance(types, Iterable):
                    for type_ in types:
                        _registed_operand_types[type_] = partial(operand, self)
                else:
                    _registed_operand_types[types] = partial(operand, self)

    async def evaluate(self, msg) -> Result:
        return await _get_field_value(self, msg)

    def __hash__(self):
        return hash(self.name)

    def __repr__(self):
        if self._exp:
            return f"Field.{self.name}(exp={strftime("%Y-%m-%d %H:%M:%S", localtime(self._exp))}, PRI={self.priority})"
        return f"Field.{self.name}(PRI={self.priority})"


@define(slots=True)
class Field:
    """字段描述符

    Attributes:
        extractor: 从 `BaseEvent` 中获取值的方法。
        default: 生成默认表达式。若并列表达式中没有该字段 `build_cond` 会自动添加默认表达式。
        priority: 在多元表达式评估的优先级，0表示保持原顺序，越大越优先，越小越靠后。
        binary_semantics: `build_cond` 会由此将二元表达式类型转成其他二元表达式类型。第二个参数是二元表达式另一端的值。
        rhs_converter: `build_cond` 会由此转换二元表达式另一端的值，若声明了 `binary_semantics`，第二个参数传递的是转换后的二元表达式类型。
        operand_types: 注册类型对应的字段与二元运算符。用于当用户传入了一个非表达式的对象时，自动将其转换为表达式。
        overrides: 二元表达式评估时，若另一操作数为 `key` ，最终评估结果为 `value`。
        cache: 默认不启用缓存，传递 CacheConfig 启用缓存。
        skip_default_on_meta: 由 `on_meta` 函数注册时，不添加该字段的默认表达式。
        _requires_extractor: 声明该字段需要由模块通过 `register_extractor` 注册 `extractor`。若为 `True` 且 `extractor` 未被注册，`build_cond` 将不会自动添加默认表达式。该参数没有必要在 `core.expr` 的外部使用。
        _redirect: 重定向到其他字段。该参数无法在元类为 `PatternMatcherMeta` 的类的外部使用。
    """

    extractor: Callable[[BaseEvent], Any] = None
    default: Callable[[FieldClause], Expr | Any] = None
    priority: int = 0
    binary_semantics: Callable[[type["BinaryExpr"], Any], type["BinaryExpr"]] = None
    rhs_converter: Callable[[Any, type["BinaryExpr"], EventCategory], Any] = None
    operand_types: dict[type | Iterable[type], BinaryExpr] = None
    overrides: dict = None
    cache: CacheConfig = None
    skip_default_on_meta: bool = True
    _requires_extractor: bool = field(default=False, alias="_requires_extractor")
    _redirect: str = field(default=None, alias="_redirect")

    clause: FieldClause = field(init=False, repr=False, default=None)


_registed_operand_types = {}
fields: dict[str, Field] = {}


class PatternMatcherMeta(type):
    def __new__(cls, name, bases, namespace: dict):
        for k, v in tuple(namespace.items()):
            if isinstance(v, Field):
                if v._redirect:  # 重定向
                    fields[k] = fields[v._redirect]
                    namespace[k] = namespace[v._redirect]
                else:
                    namespace[k] = FieldClause(k, v)

        return super().__new__(cls, name, bases, namespace)


class AlwaysTrue:
    """参与二元表达式时表达式评估结果始终为 True"""

    def __repr__(self):
        return "This Binary Expr is True"


class RawCondition(Expr[NoReturn]):
    """临时包装原始条件，用于延迟转换为具体的表达式"""

    __slots__ = ("value", "priority")

    def __init__(self, value, priority=0):
        self.value = value
        self.priority = priority
        super().__init__()

    def __repr__(self):
        if self._exp:
            return f"Raw.{self.value!r}(exp={strftime("%Y-%m-%d %H:%M:%S", localtime(self._exp))}, PRI={self.priority})"
        return f"Raw.{self.value!r}(PRI={self.priority})"


class BinaryExprMeta(type):
    convert_rhs = {}

    def __init__(cls, name, bases, attrs):
        super().__init__(name, bases, attrs)

        if cls.convert_rhs:
            BinaryExprMeta.convert_rhs[cls] = cls.convert_rhs


class BinaryExpr[Left, Right, Result](Expr[Result], metaclass=BinaryExprMeta):
    """二元表达式基类"""

    __slots__ = ("negate", "left", "right", "priority", "_cache_config", "_left_val", "_right_val", "_cached_evaluate")

    convert_rhs: Callable[[Any], Any] = None

    def __init__(self, left: Left | Expr, right: Right | Expr, _negate=None):
        self.left = left
        self.right = right
        self.negate = _negate
        if isinstance(self.left, FieldClause):
            self.priority = self.left.priority
            self._cache_config: CacheConfig = self.left.field.cache
            if self._cache_config:
                self._cached_evaluate: Callable[..., CoroutineType[Any, Any, tuple[bool, dict[ContextVar, Any]]]] = (
                    async_cached(self._cache_config.cache, ignore=self._cache_config.ignore_cache, func=self._evaluate_wrapper)
                )
        else:
            self.priority = 0
            self._cache_config = None
        super().__init__()

    def __repr__(self):
        if self._exp:
            return f"{self.__class__.__name__}({self.left!r}, {self.right!r}, exp={strftime("%Y-%m-%d %H:%M:%S", localtime(self._exp))}, PRI={self.priority})"
        return f"{self.__class__.__name__}({self.left!r}, {self.right!r}, PRI={self.priority})"

    async def evaluate(self, msg) -> Result:
        # 覆盖
        if self.left.__class__ is FieldClause and (result := self.left.field.overrides) and (result := result.get(self.right)):
            return result if self.negate is None else result ^ self.negate
        # 缓存
        if self._cache_config and (not self._cache_config.skip_cache or not self._cache_config.skip_cache(self.__class__)):
            result, contextvars = await self._cached_evaluate(
                left=self.left,
                right=self.right,
                msg=msg,
                cache_key=lambda *_, **__: self._cache_config.key_func(self.__class__, self.right, msg),
            )
            for obj, value in contextvars.items():
                obj.set(value)
            return result if self.negate is None else result ^ self.negate

        result = (await self._evaluate_wrapper(left=self.left, right=self.right, msg=msg))[0]
        return result if self.negate is None else result ^ self.negate

    async def _evaluate_wrapper(self, *, left, right, msg) -> tuple[Any, dict[ContextVar, Any]]:
        from . import dispatcher

        self._left_val: Left = await left.evaluate(msg) if isinstance(left, Expr) else left
        self._right_val: Right = await right.evaluate(msg) if isinstance(right, Expr) else right
        if self._left_val.__class__ is AlwaysTrue or self._right_val.__class__ is AlwaysTrue:
            self._left_val = self._right_val = None
            return True, {}

        result = await self._evaluate_logic()
        self._left_val = self._right_val = None
        return result, (
            {(obj := getattr(dispatcher, v)): obj.get() for v in self._cache_config.contextvars} if self._cache_config else {}
        )

    @abstractmethod
    async def _evaluate_logic(self):
        raise NotImplementedError


if DEBUG and not TYPE_CHECKING:

    class DebugBinaryExpr[Left, Right, Result](BinaryExpr[Left, Right, Result]):
        async def evaluate(self, msg) -> Result:
            if (debug := _current_debug.get()) is None:
                _current_debug.set(debug := defaultdict(dict))
            debug = debug[self]

            if (
                self.left.__class__ is FieldClause
                and (result := self.left.field.overrides)
                and (result := result.get(self.right))
            ):
                debug["right"] = self.right

            elif self._cache_config and (
                not self._cache_config.skip_cache or not self._cache_config.skip_cache(self.__class__)
            ):
                result, contextvars = await self._cached_evaluate(
                    left=self.left,
                    right=self.right,
                    msg=msg,
                    cache_key=lambda *_, **__: self._cache_config.key_func(self.__class__.__name__, self.right, msg),
                )
                for obj, value in contextvars.items():
                    obj.set(value)

            else:
                result = (await self._evaluate_wrapper(left=self.left, right=self.right, msg=msg))[0]

            debug["result"] = result = result if self.negate is None else result ^ self.negate
            return result

        async def _evaluate_wrapper(self, *, left, right, msg) -> tuple[Any, dict[ContextVar, Any]]:
            from . import dispatcher

            self._left_val: Left = await left.evaluate(msg) if isinstance(left, Expr) else left
            self._right_val: Right = await right.evaluate(msg) if isinstance(right, Expr) else right
            if self._left_val.__class__ is AlwaysTrue or self._right_val.__class__ is AlwaysTrue:
                self._left_val = self._right_val = None
                return True, {}

            result = await self._evaluate_logic()

            (debug := _current_debug.get()[self])["left"] = self._left_val
            debug["right"] = self._right_val

            self._left_val = self._right_val = None
            return result, (
                {(obj := getattr(dispatcher, v)): obj.get() for v in self._cache_config.contextvars}
                if self._cache_config
                else {}
            )

    BinaryExpr = DebugBinaryExpr


class BoolExpr(Expr[bool]):
    """布尔逻辑表达式基类"""

    __slots__ = ("clauses", "priority")

    def __init__(self, *clauses):
        prcessed = []
        for c in clauses:
            if isinstance(c, self.__class__):
                prcessed.extend(c.clauses)
            else:
                prcessed.append(c if isinstance(c, Expr) else RawCondition(c))

        positives = sorted((x for x in prcessed if x.priority > 0), key=lambda x: x.priority, reverse=True)
        zeros = [x for x in prcessed if x.priority == 0]
        negatives = sorted((x for x in prcessed if x.priority < 0), key=lambda x: x.priority, reverse=True)
        self.clauses: list[Expr | BinaryExpr] = positives + zeros + negatives
        self.priority = 0
        super().__init__()

    def __repr__(self):
        if self._exp:
            return f"{self.__class__.__name__}({", ".join(repr(c) for c in self.clauses)}, exp={strftime("%Y-%m-%d %H:%M:%S", localtime(self._exp))})"
        return f"{self.__class__.__name__}({", ".join(repr(c) for c in self.clauses)})"


# endregion
# region 运算表达式
def _command_evaluate(left, right):
    from .dispatcher import current_args

    args = []
    for i, v in enumerate(right):
        if v != (arg := left[i]):
            if v.__class__ is TypeAdapter:
                with suppress(ValidationError):
                    v.validate_python(arg)
                    args.append(arg)
                    continue
            return False
    current_args.set(args)
    return True


class Equal(BinaryExpr[Any, Any | LocalizedString, bool]):
    async def _evaluate_logic(self):
        if self.left is PM.command:
            return _command_evaluate(self._left_val, self._right_val) if len(self._left_val) == len(self._right_val) else False

        elif self.left is PM.message and isinstance(self._right_val, LocalizedString):
            from .dispatcher import current_lang

            for lang, i10n in self._right_val.translations.items():
                if i10n == self._left_val:
                    current_lang.set(lang)
                    return True
            return False

        return self._left_val == self._right_val


class NotEqual(Equal):
    def __init__(self, left, right: Any | LocalizedString):
        super().__init__(left, right, True)


class In(BinaryExpr[Any, Container | Iterable | KeysView | ValuesView, bool]):
    async def _evaluate_logic(self):
        return self._left_val in self._right_val


class NotIn(In):
    def __init__(self, left, right: Container | Iterable | KeysView | ValuesView):
        super().__init__(left, right, True)


class Contains(BinaryExpr[Container | Iterable | KeysView | ValuesView, Any, bool]):
    async def _evaluate_logic(self):
        return self._right_val in self._left_val


class NotContains(Contains):
    def __init__(self, left: Container | Iterable | KeysView | ValuesView, right):
        super().__init__(left, right, True)


class PrefixOf(BinaryExpr[Sequence | str, Sequence | str, bool]):
    async def _evaluate_logic(self):
        if self.left is PM.command:
            if len(self._left_val) >= (rl := len(self._right_val)) and _command_evaluate(self._left_val, self._right_val):
                from .dispatcher import current_args

                current_args.set(self._left_val[rl:])
                return True
            return False
        if isinstance(self._left_val, str):
            return self._right_val.startswith(self._left_val)
        return is_prefix(self._left_val, self._right_val)


class NotPrefixOf(PrefixOf):
    def __init__(self, left: Sequence | str, right: Sequence | str):
        super().__init__(left, right, True)


class SuffixOf(BinaryExpr[Sequence | str, Sequence | str, bool]):
    async def _evaluate_logic(self):
        if isinstance(self._left_val, str):
            return self._right_val.endswith(self._left_val)
        return is_suffix(self._left_val, self._right_val)


class NotSuffixOf(SuffixOf):
    def __init__(self, left: Sequence | str, right: Sequence | str):
        super().__init__(left, right, True)


"""
class SubClassOf(BinaryExpr[type, type | tuple[type, ...], bool]):
    async def _evaluate_logic(self):
        return issubclass(self._left_val, self._right_val)


class NotSubClassOf(SubClassOf):
    def __init__(self, left, right):
        super().__init__(left, right, True)


class SuperClassOf(BinaryExpr[type, type, bool]):
    async def _evaluate_logic(self):
        return issubclass(self._right_val, self._left_val)


class NotSuperClassOf(SuperClassOf):
    def __init__(self, left, right):
        super().__init__(left, right, True)


class InstanceOf(BinaryExpr[Any, type | tuple[type, ...], bool]):
    async def _evaluate_logic(self):
        return isinstance(self._left_val, self._right_val)


class NotInstanceOf(InstanceOf):
    def __init__(self, left, right):
        super().__init__(left, right, True)


class HasInstance(BinaryExpr[type | tuple[type, ...], Any, bool]):
    async def _evaluate_logic(self):
        return isinstance(self._right_val, self._left_val)


class NotHasInstance(HasInstance):
    def __init__(self, left, right):
        super().__init__(left, right, True)
"""


class SingletonOf(BinaryExpr[Sequence, Any, bool]):
    async def _evaluate_logic(self):
        if len(self._left_val) != 1:
            return False
        if self.left is PM.command and self._right_val.__class__ is TypeAdapter:
            from .dispatcher import current_args

            try:
                self._right_val.validate_python(self._left_val[0])
                current_args.set((self._left_val[0],))
                return True
            except ValidationError:
                return False

        return self._left_val[0] == self._right_val


class NotSingletonOf(SingletonOf):
    async def _evaluate_logic(self):
        if len(self._left_val) != 1:
            return True
        if self.left is PM.command and self._right_val.__class__ is TypeAdapter:
            from .dispatcher import current_args

            try:
                self._right_val.validate_python(self._left_val[0])
                current_args.set((self._left_val[0],))
                return False
            except ValidationError:
                return True

        return self._left_val[0] != self._right_val


def _convert_pattern_rhs(value):
    if isinstance(value, LocalizedString):
        value.patterns  # 触发正则表达式编译
        return value
    return re.compile(str(value), re.I)


class Match(BinaryExpr[str, re.Pattern, re.Match | None]):
    convert_rhs = _convert_pattern_rhs

    async def _evaluate_logic(self):
        from .dispatcher import current_lang, current_match

        if isinstance(self._right_val, LocalizedString):
            for lang, pattern in self._right_val.patterns.items():
                if match := pattern.match(self._left_val):
                    current_match.set(match)
                    current_lang.set(lang)
                    return match
            return None

        current_match.set(match := self._right_val.match(self._left_val))
        return match


class FullMatch(BinaryExpr[str, re.Pattern, re.Match | None]):
    convert_rhs = _convert_pattern_rhs

    async def _evaluate_logic(self):
        from .dispatcher import current_lang, current_match

        if isinstance(self._right_val, LocalizedString):
            for lang, pattern in self._right_val.patterns.items():
                if match := pattern.fullmatch(self._left_val):
                    current_match.set(match)
                    current_lang.set(lang)
                    return match
            return None

        current_match.set(match := self._right_val.fullmatch(self._left_val))
        return match


class Search(BinaryExpr[str, re.Pattern, re.Match | None]):
    convert_rhs = _convert_pattern_rhs

    async def _evaluate_logic(self):
        from .dispatcher import current_lang, current_match

        if isinstance(self._right_val, LocalizedString):
            for lang, pattern in self._right_val.patterns.items():
                if match := pattern.search(self._left_val):
                    current_match.set(match)
                    current_lang.set(lang)
                    return match
            return None

        current_match.set(match := self._right_val.search(self._left_val))
        return match


class ValidateBy[Value](BinaryExpr[Value, TypeAdapter, Value | None]):
    convert_rhs = lambda x: x if isinstance(x, TypeAdapter) else TypeAdapter(x)

    async def _evaluate_logic(self):
        try:
            return self._right_val.validate_python(self._left_val)
        except ValidationError:
            return None


class ApplyTo[Value, Result](BinaryExpr[Value, Callable[[Value], Result], Result]):
    async def _evaluate_logic(self):
        return self._right_val(self._left_val)


class GetAttr[Obj](BinaryExpr[Obj, str, Any]):
    def __call__(self, *args, **kwargs):
        return Call(self, args, kwargs)

    async def _evaluate_logic(self):
        return getattr(self._left_val, self._right_val)


class Call(BinaryExpr[Callable, tuple[tuple, dict], Any]):
    def __init__(self, func: Callable, args, kwargs):
        super().__init__(func, None)
        self.right = (args, kwargs)

    def __repr__(self):
        if self._exp:
            return f"{self.left!r} {self.__class__.__name__} {self.args} {self.kwargs}(exp={strftime("%Y-%m-%d %H:%M:%S", localtime(self._exp))}, PRI={self.priority})"
        return f"{self.left!r} {self.__class__.__name__} {self.args} {self.kwargs}(PRI={self.priority})"

    async def _evaluate_logic(self):
        return await async_run_func(self._left_val, *self._right_val[0], **self._right_val[1])


# endregion
# region 逻辑表达式
class And(BoolExpr):
    async def evaluate(self, msg):
        return await async_all(await clause.evaluate(msg) for clause in self.clauses)


class Or(BoolExpr):
    async def evaluate(self, msg):
        return await async_any(await clause.evaluate(msg) for clause in self.clauses)


class Not(Expr):
    __slots__ = ("clause", "priority")

    def __init__(self, clause):
        self.clause = clause if isinstance(clause, Expr) else RawCondition(clause)
        self.priority = clause.priority

    def __repr__(self):
        if self._exp:
            return f"Not({repr(self.clause)}, exp={strftime("%Y-%m-%d %H:%M:%S", localtime(self._exp))}, PRI={self.priority})"
        return f"Not({repr(self.clause)}, PRI={self.priority})"

    async def evaluate(self, msg):
        return not await self.clause.evaluate(msg)


def and_(*clauses):
    return And(*clauses)


def or_(*clauses):
    return Or(*clauses)


def not_(clause):
    return Not(clause)


# endregion
# region 字段作用方法


# region 默认表达式工厂
def _groups_default_factory(f: Expr):
    from .dispatcher import current_module

    if l := cfg.get_group_whitelist(m := current_module.get()):
        return f.in_(l)
    return f.notin(l) if (l := cfg.get_group_blacklist(m)) else None


def _users_default_factory(f: Expr):
    from .dispatcher import current_module

    if l := cfg.get_user_whitelist(m := current_module.get()):
        return f.in_(l)
    return f.notin(l) if (l := cfg.get_user_blacklist(m)) else None


# endregion
# region 字段右端值转换器
def _convert_type_rhs(value, __, category):
    if isinstance(value, EventType):
        return value

    if isinstance(value, str):
        match category:
            case EventCategory.CHAT:
                return MessageEventType(value)
            case EventCategory.NOTICE:
                return NoticeEventType(value)
            case EventCategory.REQUEST:
                return RequestEventType(value)
            case EventCategory.META:
                return MetaEventType(value)
            case _:
                raise ValueError(_("expr.build.convert_right.404") % value)
    return value


def _convert_sub_type_rhs(value, __, category):
    if isinstance(value, EventSubType):
        return value

    if isinstance(value, str):
        match category:
            case EventCategory.CHAT:
                return MessageSubType(value)
            case EventCategory.NOTICE:
                return NoticeSubType(value)
            case EventCategory.REQUEST:
                return RequestSubType(value)
            case EventCategory.META:
                return LifecycleSubType(value)
            case _:
                raise ValueError(_("expr.build.convert_right.404") % value)
    return value


def _convert_command_rhs(value, operand, category):
    assert category is EventCategory.CHAT

    if issubclass(operand, (Equal, PrefixOf)):
        if isinstance(value, Expr):
            return value
        if isinstance(value, Iterable) and not isinstance(value, MutableSequence):
            value = list(value)
        for i, v in enumerate(value):
            if not isinstance(v, str):
                if args := getattr(v, "__args__", None):
                    v.__args__ = tuple(str if a is Text else a for a in args)
                value[i] = TypeAdapter(v)
    elif issubclass(operand, SingletonOf) and not isinstance(value, str):
        if args := getattr(value, "__args__", None):
            value.__args__ = tuple(str if a is Text else a for a in args)
        value = TypeAdapter(value)
    return value


# endregion
# region 字段二元运算符转换器
def _convert_to_singletonof(operator, right):
    if isinstance(right, str) or not isinstance(right, Sequence):
        if operator is Equal:
            return SingletonOf
        elif operator is NotEqual:
            return NotSingletonOf
    return operator


def _convert_to_validate(operator, right):
    if isinstance(right, (type, GenericAlias, UnionType, _Final, _UnionGenericAlias)):
        if operator is Equal:
            return ValidateBy
    return operator


# endregion
# region 限速
cfg.register("limit", 3, _("expr.fields.limit.cfg_comment"), module="aha")


class MsgLimit(dbBase):
    __tablename__ = "message_limit"
    platform = Column(String, primary_key=True)
    user_id = Column(String, primary_key=True)
    count = Column(Integer, default=1)
    last_time = Column(Float)


async def _check_rate_limit(msg: BaseEvent):
    """被限速 => False，正常状态 => True"""
    if not cfg.limit or not hasattr(msg, "user_id") or await _is_admin(msg):
        return True
    current_time = time()
    async with db_sessionmaker() as session:
        result = await session.execute(
            update(MsgLimit)
            .where(MsgLimit.platform == msg.platform, MsgLimit.user_id == msg.user_id, MsgLimit.last_time <= current_time - 60)
            .values(count=1, last_time=current_time)
            .returning(MsgLimit.count)
        )
        if result.scalar_one_or_none() is not None:
            await session.commit()
            return True

        result = await session.execute(
            update(MsgLimit)
            .where(MsgLimit.platform == msg.platform, MsgLimit.user_id == msg.user_id)
            .values(count=MsgLimit.count + 1, last_time=current_time)
            .returning(MsgLimit.count)
        )
        if (updated_count := result.scalar_one_or_none()) is not None:
            await session.commit()
            return updated_count <= cfg.get("limit", module="aha")

        await session.execute(insert(MsgLimit).values(platform=msg.platform, user_id=msg.user_id, last_time=current_time))
        await session.commit()
        return True


# endregion
# region 消息处理
cprms: ContextVar[str] = ContextVar("aha_prefix_removed_str_msg", default=None)
cprmc: ContextVar[MessageChain] = ContextVar("aha_prefix_removed_msg_chain", default=None)


def get_msg_str_without_prefix(msg: MessageChain):
    from .dispatcher import current_event

    if (cache := msg is current_event.get().message) and (moded := cprms.get()):
        return moded
    moded = str(remove_msg_seq_prefix(msg))
    if cache:
        cprms.set(moded)
    return moded


def remove_msg_seq_prefix(msg: MessageChain):
    from .dispatcher import current_event, current_module, cugp

    if (prefix := cfg.global_msg_prefix if cugp.get() else cfg.get_msg_prefix(current_module.get())) is None:
        return msg
    # 缓存
    if (cache := (event := current_event.get()).message is msg) and (moded := cprmc.get()) is not None:
        return moded

    moded = None
    i, text = find_first_instance(msg, Text)
    # 去除@bot前缀
    if (at := find_first_instance(msg, At, end_index=i)[1]) and at.user_id == event.self_id:
        del (moded := msg.copy())[0]
        i -= 1
        moded[i] = text = text.model_copy()
        text.text = text.text.lstrip()
    # 去除文本前缀
    if prefix and text and text.text:
        # 去除前缀
        if len(prefix) == 1:
            if halfwidth(text.text[0]) == prefix:
                if not moded:
                    (moded := msg.copy())[i] = text = text.model_copy()
                text.text = text.text[1:].lstrip()
                if not text.text:
                    del moded[i]
        elif text.text.startswith(prefix):
            if not moded:
                (moded := msg.copy())[i] = text = text.model_copy()
            text.text = text.text[len(prefix) :].lstrip()
            if not text.text:
                del moded[i]

    if moded is None:
        moded = msg
    if cache:
        cprmc.set(moded)
    return moded


# endregion
def _has_msg_prefix(event: Message):
    from .dispatcher import current_module, cugp

    if event.message:
        if (prefix := cfg.global_msg_prefix if cugp.get() else cfg.get_msg_prefix(current_module.get())) is None:
            return True
        i, text = find_first_instance(event.message, Text)
        if (at := find_first_instance(event.message, At, end_index=i)[1]) and at.user_id == event.self_id:
            return True
        if prefix and text and text.text:
            return halfwidth(text.text[0]) == prefix if len(prefix) == 1 else text.text.startswith(prefix)
    return False


async def _gid(event: BaseEvent):
    return await group2aha_id(event.platform, event.group_id)


async def _uid(event: BaseEvent):
    return await user2aha_id(event.platform, event.user_id)


@async_cached(
    LRUCache(cfg.register("admin", 32768, _("expr.fields.admin.cache.cfg_comment"), module="cache")),
    lambda event: (getattr(event, "user_id", None), getattr(event, "group_id", None), event.platform),
)
async def _is_admin(event: BaseEvent):
    if (uid := getattr(event, "user_id", None)) and (gid := getattr(event, "group_id", None)):
        from .api import API

        return await API.is_admin(gid, uid)


async def _is_super(_):
    from .perms import is_super

    return await is_super()


def _msg2command(event: Message):
    command = []
    for m in remove_msg_seq_prefix(event.message):
        if isinstance(m, Text):
            splited = m.text.partition("\n")
            command.extend(s.strip() for s in splited[0].split(" "))
            if splited[1]:
                command.append(f"{command.pop()}\n{splited[2]}")
        else:
            command.append(m)
    return command


# endregion
# region private
def _wrap_conditions(conditions, event_type: EventCategory):
    """包装原始条件"""

    def recursion(expr, is_first_level=False):
        if isinstance(expr, And):
            return And(*[converted for c in expr.clauses if (converted := recursion(c)) is not None])

        elif isinstance(expr, Or):
            return Or(*[converted for c in expr.clauses if (converted := recursion(c)) is not None])

        elif isinstance(expr, Not):
            return None if (converted := recursion(expr.clause)) is None else Not(converted)

        elif isinstance(expr, BinaryExpr):
            expr.left, expr.right = _adjust_binary_field(expr.left, expr.right)
            expr.left = recursion(expr.left)
            if expr.left is None or expr.right is None:
                return None

            # 将形似 PM.message == Or("a", "b") 转化为 Or(PM.message == "a", PM.message == "b")
            if isinstance(expr.right, BoolExpr):
                conds = []
                for r in expr.right.clauses:
                    if expr.left.field.binary_semantics:
                        operand = expr.left.field.binary_semantics(expr.__class__, r)
                    else:
                        operand = expr.__class__
                    if converter := BinaryExprMeta.convert_rhs.get(expr.__class__):
                        r = converter(r)
                    if expr.left.field.rhs_converter:
                        r = expr.left.field.rhs_converter(r, operand, event_type)
                    conds.append(recursion(operand(expr.left, r)))
                return expr.right.__class__(*conds)

            if expr.left.__class__ is FieldClause:
                if expr.left.field.binary_semantics:
                    operand = expr.left.field.binary_semantics(expr.__class__, expr.right)
                else:
                    operand = expr.__class__
                if converter := BinaryExprMeta.convert_rhs.get(expr.__class__):
                    expr.right = converter(expr.right)
                if expr.left.field.rhs_converter:
                    expr.right = expr.left.field.rhs_converter(expr.right, operand, event_type)
                return operand(expr.left, expr.right)

            return expr

        elif is_first_level or isinstance(expr, RawCondition) and (expr := expr.value) is not None:
            for t, f in _registed_operand_types.items():
                if isinstance(expr, t):
                    return recursion(f(expr))

        return expr

    # 处理顶层条件
    processed = []
    root_strings = []
    for cond in conditions:
        if isinstance(cond, str) and (processed or event_type is not EventCategory.CHAT):
            root_strings.append(cond)
        else:
            processed.append(recursion(cond, True))

    # 特殊处理
    if root_strings:
        # [0] -> 类型，[1] -> 子类型
        processed.append(recursion(Equal(PM.type_, root_strings[0])))
        if len(root_strings) >= 2:
            processed.append(recursion(Equal(PM.sub_type, root_strings[1])))

    # 去重校验
    seen_fields = set()
    final_conditions = []
    for expr in processed:
        if expr is None:
            continue
        if isinstance(expr, Equal) and expr.left.__class__ is FieldClause:
            if expr.left in seen_fields:
                continue
            seen_fields.add(expr.left)
        final_conditions.append(expr)

    return final_conditions


def _collect_used_fields(expr):
    used = []
    if isinstance(expr, FieldClause):
        used.append(expr)
    elif isinstance(expr, BoolExpr):
        for clause in expr.clauses:
            used.extend(_collect_used_fields(clause))
    elif isinstance(expr, Not):
        used.extend(_collect_used_fields(expr.clause))
    elif isinstance(expr, BinaryExpr):
        used.extend(_collect_used_fields(expr.left))
        used.extend(_collect_used_fields(expr.right))
    return used


async def _get_field_value(field: FieldClause, msg: BaseEvent):
    if field.field.extractor is None and field.field._requires_extractor:
        return True
    return await async_run_func(field.field.extractor, msg)


def _adjust_binary_field(left, right) -> tuple[FieldClause | Expr | Any, FieldClause | Expr | Any]:
    # 将 FieldClause 转到左侧
    left_is_field = left.__class__ is FieldClause
    right_is_field = right.__class__ is FieldClause
    if left_is_field and right_is_field:
        raise ValueError(_("expr.build.adjust_order.exceed"))

    if left_is_field:
        return left, right
    elif right_is_field:
        return right, left

    # 若没有 FieldClause，将 Expr 转到左侧
    right_is_expr = isinstance(right, Expr)
    return left if isinstance(left, Expr) or not right_is_expr else right, left if right_is_expr else right


# region 缓存
if TYPE_CHECKING:

    class CacheIgnoreKwargs(TypedDict, total=False):
        left: Any
        right: Any
        msg: BaseEvent


@define(slots=True)
class CacheConfig:
    """二元表达式评估结果缓存配置，用于字段属性

    Attributes:
        cache: 继承自 `cachetools.Cache` 的缓存器。
        key_func: 生成缓存键的函数，接收运算符的类、表达式中第二个操作数和 `msg`。
        ignore_cache: 决定是否缓存结果的函数，接收 `评估结果, left, right, msg`，后三项参数以 kwargs 传递。
        skip_cache: 决定是否执行缓存相关逻辑。
        contextvars: 同时缓存指定的 ContextVar。
    """

    cache: Any
    key_func: Callable[[type[BinaryExpr], Any, BaseEvent], Hashable] = lambda operator, right, _: hashkey(operator, right)
    ignore_cache: Callable[[Any, Unpack[CacheIgnoreKwargs]], bool] = None
    skip_cache: Callable[[type[BinaryExpr]], bool] = None
    contextvars: Iterable[str] = None


"""async def _hash_evaluate(msg, expr):
    extractors = set()
    results = []
    for field in fields.values():
        if field.extractor not in extractors:
            results.append(await async_run_func(field.extractor, msg))
    return hashkey(expr, *results)"""


# endregion
# endregion
# region public
class PM(metaclass=PatternMatcherMeta):
    """条件字段定义

    Attributes:
        message: 以绝对字符串限定 `message_str`。
        command: 以命令/参数形式限定 `message`。
        pattern: 以正则表达式限定 `message_str`。
        request: `request_type`
        notice: `notice_type`
        meta: `meta_event_type`
        sub_type: `sub_type`

        isgroup: 是否为群聊消息。
        isprivate: 是否为私聊消息。依据 `cfg.allow_private` 是否默认匹配私聊消息。
        uid: 事件触发者的 Aha ID。
        gid: 事件触发群聊的 Aha ID。
        group: 提取值为 `models.core.Group` 对象，消息来源为群聊时默认限定黑白名单。
        user: 提取值为 `models.core.User` 对象，默认限定黑白名单。
        platform: 事件来源平台名字符串。
        bot: 第一个接收到该事件的 bot ID，来自 core.ipc.bots.keys()

        prefix: 消息前缀是否为 `cfg.get_msg_prefix()` 或@机器人。
        validated: 事件触发者是否已通过验证，默认限定通过验证的。第二个操作数为 False 时跳过提取逻辑。需要通过模块注册回调，若没有模块注册则无效。
        limit: 事件触发者是否遵循全局限速。默认遵循。未限定 `message`、`request_type`、`notice_type` 和 `sub_type` 时务必声明 `PM.limit == False`。
        admin: 事件触发者是否是群管理员。
        super: 事件触发者是否是 Aha 超级用户。
    """

    # region 内容匹配字段
    message: FieldClause[str] = Field(
        lambda event: get_msg_str_without_prefix(event.message) if isinstance(event, Message) else None,
        operand_types={(LocalizedString, str, re.Pattern): FullMatch},
        cache=CacheConfig(
            LRUCache(cfg.register("message_match", 2048, _("expr.fields.msg.cache"), module="cache")),
            lambda operator, right, event: hashkey(operator, right, event.message_str),
            skip_cache=lambda operator: not issubclass(operator, (FullMatch, Match, Search)),
            contextvars=("current_match", "current_lang"),
        ),
    )
    msg: FieldClause[str] = Field(_redirect="message")
    message_str: FieldClause[str] = Field(_redirect="message")
    msg_str: FieldClause[str] = Field(_redirect="message")
    message_chain: FieldClause[MessageChain] = Field(
        lambda event: remove_msg_seq_prefix(event.message) if isinstance(event, Message) else None,
        binary_semantics=_convert_to_validate,
        operand_types={(type, GenericAlias, UnionType, TypeAdapter, _Final, _UnionGenericAlias): ValidateBy},
    )
    msg_chain: FieldClause[MessageChain] = Field(_redirect="message_chain")
    command: FieldClause[list[str | MsgSeg]] = Field(
        _msg2command,
        binary_semantics=_convert_to_singletonof,
        rhs_converter=_convert_command_rhs,
        operand_types={(list, tuple): Equal},
    )
    # endregion
    # region 类型匹配字段
    type_: FieldClause[EventType] = Field(
        lambda event: event.event_type, rhs_converter=_convert_type_rhs, operand_types={EventType: Equal}, priority=39
    )
    request: FieldClause[RequestEventType] = Field(_redirect="type_")
    notice: FieldClause[NoticeEventType] = Field(_redirect="type_")
    meta: FieldClause[MetaEventType] = Field(_redirect="type_")
    sub_type: FieldClause[EventSubType] = Field(
        lambda event: getattr(event, "sub_type", None),
        rhs_converter=_convert_sub_type_rhs,
        operand_types={EventSubType: Equal},
        priority=40,
    )
    # endregion
    # region 来源限定字段
    isgroup: FieldClause[bool] = Field(lambda event: bool(getattr(event, "group_id", False)), priority=6)
    isprivate: FieldClause[bool] = Field(
        lambda event: not bool(getattr(event, "group_id", False)),
        None if cfg.register("private", True, _("expr.fields.isprivate.default_cfg"), module="aha") else (lambda v: v == False),
        priority=7,
    )
    gid: FieldClause[int] = Field(_gid, priority=3)
    uid: FieldClause[int] = Field(_uid, priority=2)
    group: FieldClause[Group] = Field(
        lambda event: (Group(event.platform, group_id) if (group_id := getattr(event, "group_id", None)) else AlwaysTrue()),
        _groups_default_factory,
        priority=5,
    )
    user: FieldClause[User] = Field(
        lambda event: User(event.platform, getattr(event, "user_id", None)),
        _users_default_factory,
        priority=4,
    )
    platform: FieldClause[str] = Field(lambda event: event.platform, priority=8)
    bot: FieldClause[int] = Field(lambda event: event.bot_id, priority=10)
    # endregion
    # region 功能控制字段
    prefix: FieldClause[bool] = Field(_has_msg_prefix)  # 消息内容相关的都别设置优先级
    admin: FieldClause[bool] = Field(_is_admin, priority=-50)
    super: FieldClause[bool] = Field(_is_super, priority=50)
    validated: FieldClause[bool] = Field(default=lambda v: v == True, _requires_extractor=True, priority=-10)
    limit: FieldClause[bool] = Field(
        _check_rate_limit,
        (lambda v: v == True) if cfg.get("limit", module="aha") else None,
        overrides={False: True},
        priority=-999,
    )
    # endregion


Pmessage: FieldClause[str] = PM.message
Pmsg: FieldClause[str] = PM.message
Pmsg_chain: FieldClause[MessageChain] = PM.message_chain
Pcommand: FieldClause[list] = PM.command
Prequest: FieldClause[RequestEventType] = PM.request
Pnotice: FieldClause[NoticeEventType] = PM.notice
Pmeta: FieldClause[MetaEventType] = PM.meta
Psub_type: FieldClause[EventSubType] = PM.sub_type
Pisgroup: FieldClause[bool] = PM.isgroup
Pisprivate: FieldClause[bool] = PM.isprivate
Pgid: FieldClause[int] = PM.gid
Puid: FieldClause[int] = PM.uid
Pgroup: FieldClause[Group] = PM.group
Puser: FieldClause[User] = PM.user
Pplatform: FieldClause[str] = PM.platform
Pbot: FieldClause[int] = PM.bot
Pprefix: FieldClause[bool] = PM.prefix
Padmin: FieldClause[bool] = PM.admin
Psuper: FieldClause[bool] = PM.super
Pvalidated: FieldClause[bool] = PM.validated
Plimit: FieldClause[bool] = PM.limit


def field_exists(expr: Expr | Any, field: FieldClause | Iterable[FieldClause]) -> bool:
    """检查表达式中是否存在指定字段"""
    if isinstance(expr, BoolExpr):
        return any(field_exists(c, field) for c in expr.clauses)
    elif isinstance(expr, BinaryExpr):
        return field_exists(expr.left, field) or field_exists(expr.right, field)
    elif isinstance(expr, Not):
        return field_exists(expr.clause, field)
    return expr is field or not isinstance(field, FieldClause) and any(expr is x for x in field)


def binary_expr_exists(expr: Expr | Any, binary_expr: type[BinaryExpr] | Iterable[type[BinaryExpr]]) -> bool:
    """检查表达式中是否存在指定二元表达式类型"""
    if isinstance(expr, BoolExpr):
        return any(binary_expr_exists(c, binary_expr) for c in expr.clauses)
    elif binary_expr.__class__ is type and isinstance(expr, binary_expr) or any(isinstance(expr, x) for x in binary_expr):
        return True
    elif isinstance(expr, BinaryExpr):
        return binary_expr_exists(expr.left, binary_expr) or binary_expr_exists(expr.right, binary_expr)
    elif isinstance(expr, Not):
        return binary_expr_exists(expr.clause, binary_expr)
    return False


def modify_expr(expr: Expr, *overrides: BinaryExpr):
    """递归修改表达式中的字段，第二个操作数为 `None` 时删除该字段的表达式"""

    def recursive(expr, left, right):
        if isinstance(expr, BoolExpr):
            new_clauses = []
            modified = False
            for clause in expr.clauses:
                if (new_expr := (result := recursive(clause, left, right))[0]) is not None:
                    new_clauses.append(new_expr)
                if result[1]:
                    modified = True
            return expr.__class__(*new_clauses) if modified else expr, modified
        elif isinstance(expr, Not):
            if (result := recursive(expr.clause, left, right))[1]:
                return None if (result := result[0]) is None else Not(result), True
        elif isinstance(expr, BinaryExpr) and expr.left is left and expr.right != right:
            return None if right is None else expr.__class__(expr.left, right), True
        return expr, False

    for override in overrides:
        exp = expr._exp
        expr = recursive(expr, *_adjust_binary_field(override.left, override.right))[0]
        expr._exp = exp
    return expr


def build_cond(
    conditions: Iterable[Expr | str | re.Pattern], event_type: EventCategory, exp: float | None = None, debug: bool = False
) -> Expr:
    """构建条件"""
    conditions = _wrap_conditions(conditions, event_type)
    used_field = {item for cond in conditions for item in _collect_used_fields(cond)}
    default_clauses = [
        default_value
        for field in fields.values()
        if field.default is not None
        and not (field.skip_default_on_meta and event_type is EventCategory.META)
        and (not field._requires_extractor or field.extractor)
        and field.clause not in used_field
        and (default_value := field.default(field.clause)) is not None
    ]

    if len(conditions := conditions + default_clauses) == 1:
        cond: Expr = conditions[0]
    else:
        cond = And(*conditions)

    cond._exp = exp if exp is None or exp >= 1000000000 else (time() + exp)
    if debug:
        cond.debug = debug

    return cond


# region 重定向 extractor
extractor_registrations: defaultdict[FieldClause, dict[str, Callable]] = defaultdict(dict)


def register_extractor(field: FieldClause):
    """注册指定字段 `extractor` 的装饰器"""

    if field.field._requires_extractor:

        def decorator(func):
            if (module := AHA_MODULE_PATTERN.match(func.__module__)[1]) in (extractors := extractor_registrations[field]):
                _logger.warning(_("expr.register_extractor.duplicate") % {"field": field.name, "module": module})
                return func
            extractors[module] = func
            cfg.register(field.name, Option(extractors), module="expr_extractors")
            return func

        return decorator
    raise RuntimeError(_("expr.register_extractor.403") % {"field": field.name})


def redirect_extractors():
    """重定向所有字段的 extractor"""
    for field, extractors in extractor_registrations.items():
        field.field.extractor = extractors[cfg.register(field.name, module="expr_extractors")]
        for key in extractors:
            if (value := cfg._data.get(f"modules.{key}")) and field.name in value:
                value.pop(field.name)


# endregion
# @async_cached(expr_cache, key=hash_evaluate)
if DEBUG and not TYPE_CHECKING:
    from pprint import pprint

    async def evaluate(event: BaseEvent, expr: Expr | BoolExpr, token: int = None, pool: ExprPool = None) -> bool | None:
        """评估表达式入口"""
        if expr._exp and pool and expr._exp <= time():
            await pool.remove_key(expr)
            return None
        try:
            result = await expr.evaluate(event)
            if expr._debug:
                pprint(dict(_current_debug.get()))
            _current_debug.set(None)
            if result:
                if pool:
                    if token and token not in pool.token_map:
                        result = None
                    if expr._exp:
                        await pool.remove_key(expr)
                return result
        except Exception:
            _logger.exception(_("expr.evaluate.error"))
        return False

else:

    async def evaluate(event, expr: Expr | BoolExpr, token=None, pool: ExprPool = None) -> bool | None:
        """评估表达式入口"""
        if expr._exp and pool and expr._exp <= time():
            await pool.remove_key(expr)
            return None
        with suppress(Exception):
            if result := await expr.evaluate(event):
                if pool:
                    if token and token not in pool.token_map:
                        result = None
                    if expr._exp:
                        await pool.remove_key(expr)
                return result
        return False


# endregion
