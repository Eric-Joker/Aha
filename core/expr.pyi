import re
from abc import abstractmethod
from collections.abc import Callable, Container, Hashable, ItemsView, Iterable, KeysView, Mapping, Sequence, ValuesView
from types import GenericAlias, UnionType
from typing import Any, Literal, NoReturn, SupportsIndex, TypedDict, Unpack, _Final, _UnionGenericAlias

from attrs import define
from pydantic import TypeAdapter

from core.i18n import LocalizedString
from models.api import BaseEvent, EventSubType, EventType
from models.core import EventCategory, Group, User
from models.msg import MsgSeq, MsgSeg
from utils.typekit import Strable

from .router import ExprPool

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
    "Match",
    "FullMatch",
    "Search",
    "ValidateBy",
    "Filter",
    "ApplyTo",
    "And",
    "Or",
    "Not",
    "and_",
    "or_",
    "not_",
    "Equal",
    "NotEqual",
    "evaluate",
    "modify_expr",
    "field_exists",
    "register_extractor",
)

class Expr[Result]:
    exp: float | None
    debug: bool

    def modify(self, *overrides: BinaryExpr) -> Expr: ...
    def has_field(self, field: FieldClause) -> bool: ...
    @abstractmethod
    async def evaluate(self, msg: BaseEvent) -> Result: ...
    def __and__(self, other: Any) -> And: ...
    def __or__(self, other: Any) -> Or: ...
    def __invert__(self) -> Not: ...
    def __eq__(self, other: Any) -> Equal: ...
    def __ne__(self, other: Any) -> NotEqual: ...
    def __getitem__(self, item: Any) -> Getitem: ...
    def in_(self, other: Any) -> In: ...
    def notin(self, other: Any) -> NotIn: ...
    def contains(self: Expr[Container | Iterable | KeysView | ValuesView], other: Any) -> Contains: ...
    def notcontains(self: Expr[Container | Iterable | KeysView | ValuesView], other: Any) -> NotContains: ...
    def prefixof(self: Expr[Sequence | str], seq: Sequence | str) -> PrefixOf: ...
    def notprefixof(self: Expr[Sequence | str], seq: Sequence | str) -> NotPrefixOf: ...
    def suffixof(self: Expr[Sequence | str], seq: Sequence | str) -> SuffixOf: ...
    def notsuffixof(self: Expr[Sequence | str], seq: Sequence | str) -> NotSuffixOf: ...
    def singletonof(self: Expr[Sequence], obj: Any) -> SingletonOf: ...
    def notsingletonof(self: Expr[Sequence], obj: Any) -> NotSingletonOf: ...
    def match(self: Expr[str], obj: Strable | re.Pattern) -> Match: ...
    def fullmatch(self: Expr[str], obj: Strable | re.Pattern) -> FullMatch: ...
    def search(self: Expr[str], obj: Strable | re.Pattern) -> Search: ...
    def validateby(self, obj: type | GenericAlias | UnionType | TypeAdapter | _Final | _UnionGenericAlias) -> ValidateBy: ...
    def filter[T: Container | Iterable | KeysView | ValuesView | ItemsView](
        self: Expr[T], function: Callable[[Any], bool]
    ) -> ApplyTo[T, Iterable]: ...
    def to_str(self) -> ApplyTo[Any, str]: ...
    def to_msg_seq[T: Iterable | str | MsgSeg](self: Expr[T]) -> ApplyTo[T, MsgSeq]: ...
    def applyto[Value, Result](self: Expr[Value], obj: Callable[[Value], Result]) -> ApplyTo[Value, Result]: ...

class FieldClause[Result](Expr[Result]):
    name: str
    field: Field
    priority: int

    def __init__(self, name: str, field: Field) -> None: ...
    async def evaluate(self, msg: BaseEvent) -> Result: ...

class Field:
    extractor: Callable[[BaseEvent], Any] | None
    default: Callable[[FieldClause], Expr | bool] | None
    requires_extractor: bool
    overrides: dict[Any, Any] | None
    rhs_converter: Callable[[Any, type[BinaryExpr], EventCategory], Any] | None
    priority: int
    binary_semantics: Callable[[type[BinaryExpr], Any], type[BinaryExpr]] | None
    operand_types: dict[type | Iterable[type], BinaryExpr] | None
    cache: CacheConfig | None
    skip_default_on_meta: bool
    unique: bool
    redirect: str | None

    def __init__(
        self,
        extractor: Callable[[BaseEvent], Any] | None = None,
        default: Callable[[FieldClause], Expr | bool] | None = None,
        priority: int = 0,
        binary_semantics: Callable[[type[BinaryExpr], Any], type[BinaryExpr]] | None = None,
        rhs_converter: Callable[[Any, type[BinaryExpr], EventCategory], Any] | None = None,
        operand_types: dict[type | Iterable[type], BinaryExpr] | None = None,
        overrides: dict[Any, Any] | None = None,
        cache: CacheConfig | None = None,
        requires_extractor: bool = False,
        skip_default_on_meta: bool = True,
        unique: bool = False,
        redirect: str | None = None,
    ) -> None: ...

class PatternMatcherMeta(type):
    def __new__(cls, name: str, bases: tuple[type, ...], namespace: dict[str, Any]) -> type: ...

class AlwaysTrue: ...

class RawCondition(Expr[NoReturn]):
    value: Any
    priority: int

    def __init__(self, value: Any, priority: int = 0) -> None: ...
    async def evaluate(self, msg: BaseEvent) -> NoReturn: ...

class BinaryExpr[Left, Right, Result](Expr[Result]):
    negate: bool | None
    left: Left | Expr
    right: Right | Expr
    priority: int

    def __init__(self, left: Left | Expr, right: Right | Expr, _negate: bool | None = None) -> None: ...
    async def evaluate(self, msg: BaseEvent) -> Result: ...

class BoolExpr(Expr[bool]):
    clauses: list[Expr | BinaryExpr]
    priority: int

    def __init__(self, *clauses: Any) -> None: ...

class Equal(BinaryExpr[Any, Any | LocalizedString, bool]): ...
class NotEqual(Equal): ...
class In(BinaryExpr[Any, Container | Iterable | KeysView | ValuesView, bool]): ...
class NotIn(In): ...
class Contains(BinaryExpr[Container | Iterable | KeysView | ValuesView, Any, bool]): ...
class NotContains(Contains): ...
class PrefixOf(BinaryExpr[Sequence | str, Sequence | str, bool]): ...
class NotPrefixOf(PrefixOf): ...
class SuffixOf(BinaryExpr[Sequence | str, Sequence | str, bool]): ...
class NotSuffixOf(SuffixOf): ...
class SingletonOf(BinaryExpr[Sequence, Any, bool]): ...
class NotSingletonOf(SingletonOf): ...
class Match(BinaryExpr[str, re.Pattern, re.Match | None]): ...
class FullMatch(BinaryExpr[str, re.Pattern, re.Match | None]): ...
class Search(BinaryExpr[str, re.Pattern, re.Match | None]): ...
class ValidateBy[Value](BinaryExpr[Value, TypeAdapter, Value | None]): ...
class ApplyTo[Value, Result](BinaryExpr[Value, Callable[[Value], Result], Result]): ...
class Getitem(BinaryExpr[Container | Iterable | Mapping, Any | SupportsIndex, Any]): ...
class And(BoolExpr): ...
class Or(BoolExpr): ...

class Not(Expr[bool]):
    clause: Expr
    priority: int

    def __init__(self, clause: Any) -> None: ...
    async def evaluate(self, msg: BaseEvent) -> bool: ...

def and_(*clauses: Any) -> And: ...
def or_(*clauses: Any) -> Or: ...
def not_(clause: Any) -> Not: ...

class CacheIgnoreKwargs(TypedDict, total=False):
    left: Any
    right: Any
    msg: BaseEvent

@define(slots=True)
class CacheConfig:
    cache: Any
    key_func: Callable[[str, Any, BaseEvent], Hashable]
    ignore_cache: Callable[[bool, Unpack[CacheIgnoreKwargs]], bool] | None
    skip_cache: Callable[[type[BinaryExpr]], bool] | None
    contextvars: tuple[Literal["current_match", "current_args", "current_lang"], ...] | None

class PM(metaclass=PatternMatcherMeta):
    __fields__: dict[str, Field]

    # 内容匹配字段
    message: FieldClause[str]
    msg: FieldClause[str]
    message_str: FieldClause[str]
    msg_str: FieldClause[str]
    message_chain: FieldClause[MsgSeq]
    msg_chain: FieldClause[MsgSeq]
    command: FieldClause[list[Any]]

    # 类型匹配字段
    type_: FieldClause[EventType]
    request: FieldClause[EventType]
    notice: FieldClause[EventType]
    meta: FieldClause[EventType]
    sub_type: FieldClause[EventSubType]

    # 来源限定字段
    isgroup: FieldClause[bool]
    isprivate: FieldClause[bool]
    gid: FieldClause[int]
    uid: FieldClause[int]
    group: FieldClause[Group]
    user: FieldClause[User]
    platform: FieldClause[str]
    bot: FieldClause[int]

    # 功能控制字段
    prefix: FieldClause[bool]
    admin: FieldClause[bool]
    super: FieldClause[bool]
    validated: FieldClause[bool]
    limit: FieldClause[bool]

Pmessage: FieldClause[str] = PM.message
Pmsg: FieldClause[str] = PM.message
Pmsg_chain: FieldClause[MsgSeq] = PM.message_chain
Pcommand: FieldClause[list[Any]] = PM.command
Prequest: FieldClause[EventType] = PM.request
Pnotice: FieldClause[EventType] = PM.notice
Pmeta: FieldClause[EventType] = PM.meta
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

def field_exists(
    expr: Expr | Any, field: FieldClause | Iterable[FieldClause], binary_expr: type[BinaryExpr] | None = None
) -> bool: ...
def modify_expr(expr: Expr, *overrides: BinaryExpr) -> Expr: ...
def build_cond(
    conditions: Iterable[Expr | str | re.Pattern], event_type: EventCategory, exp: float | None = None, debug: bool = False
) -> Expr: ...
def register_extractor(field: FieldClause) -> Callable: ...
def redirect_extractors() -> None: ...
async def evaluate(
    event: BaseEvent, expr: Expr | BoolExpr, token: int | None = None, pool: ExprPool | None = None
) -> bool | None: ...
