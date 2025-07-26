# Copyright (C) 2025 github.com/Eric-Joker
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from abc import abstractmethod
from dataclasses import dataclass
from itertools import chain
from logging import getLogger
from time import time
from typing import Any, Callable, Hashable

import regex as re
from cachetools.keys import hashkey
from humanfriendly import parse_size
from sqlalchemy import Column, Float, Integer, insert, select, update

from config import cfg
from ncatbot.core.message import GroupMessage, PrivateMessage
from ncatbot.core.notice import NoticeMessage
from ncatbot.core.request import Request
from services.database import db_session_factory, dbBase

from .cache import MemLRUCache, async_cached, get_cache
from .misc import async_run_func, convert_text
from .typekit import is_hashable, is_in_supported


# region 基类/元类
class Expr:
    """表达式基类"""

    __slots__ = ("exp",)

    def __and__(self, other):
        return And(self, other)

    def __or__(self, other):
        return Or(self, other)

    def __invert__(self):
        return Not(self)

    def __hash__(self):
        return hash((self.__class__,) + tuple(getattr(self, slot) for slot in self.__slots__))

    def modify(self, *overrides: "BinaryExpr") -> "Expr":
        """递归修改表达式中的指定字段"""
        return modify_expr(self, *overrides)

    @abstractmethod
    async def evaluate(self, msg) -> tuple[bool, list]:
        """表达式求值接口"""
        raise NotImplementedError


class FieldClause(Expr):
    """字段访问表达式"""

    __slots__ = ("name", "field", "priority")

    def __init__(self, name, field: "Field"):
        self.name = name
        self.field = field
        self.priority = field.priority

    async def evaluate(self, msg) -> tuple[bool, list]:
        return await _get_field_value(self, msg), []

    def __eq__(self, other):
        return Equal(self, other)

    def __ne__(self, other):
        return NotEqual(self, other)

    __hash__ = Expr.__hash__

    def in_(self, other):
        if is_in_supported(other):
            return Contains(self, other)
        raise TypeError("contains() argument must support the 'in' operator")

    def notin(self, other):
        if is_in_supported(other):
            return NotContains(self, other)
        raise TypeError("notcontains() argument must support the 'in' operator")


class Field:
    """字段描述符"""

    __slots__ = ("name", "type", "extractor", "default", "op", "overrides", "priority", "cache", "unique", "always_true")

    def __init__(
        self,
        type_,
        extractor: Callable,
        default=None,
        op: Callable = None,
        overrides: dict[Any:bool] = None,
        priority=0,
        cache: "CacheConfig" = None,
        unique=False,
        always_true=False,
    ):
        """
        Args:
            extractor: 从消息中获取该属性所用到的值的方法。
            default: 默认值，用于自动生成 `op`。
            op: 默认表达式，需要评估的表达式若没有该字段的则自动添加。
            overrides: 比较是否相等时，与之比较的值为 `key` 时，最终评估结果为 `value`。
            priority: 在多元表达式评估的优先级，0表示保持原顺序，正数越大越优先，负数越小越靠后。
            cache: 默认不启用缓存，传递 CacheConfig 启用缓存。
            unique: 是否在并列表达式中只能出现一次。
            always_true: 二元表达式评估时始终返回 `True`。
        """
        if overrides is None:
            overrides = {}
        self.type = type_
        self.extractor = extractor
        self.default = default
        self.op = op or (None if default is None else (lambda f: f == default))
        self.overrides = overrides
        self.priority = priority
        self.cache = cache
        self.unique = unique
        self.always_true = always_true


class ExprMeta(type):
    """表达式元类"""

    def __new__(cls, name, bases, namespace):
        fields = {}
        for k, v in list(namespace.items()):
            if isinstance(v, Field):
                v.name = k
                fields[k] = v
                namespace[k] = FieldClause(k, v)
        namespace["__fields__"] = fields
        return super().__new__(cls, name, bases, namespace)


class RawCondition(Expr):
    """临时包装原始条件，用于延迟转换为具体的表达式"""

    __slots__ = ("value", "priority")

    def __init__(self, value, priority=0):
        self.value = value
        self.priority = priority

    async def evaluate(*_):
        raise NotImplementedError("RawCondition should be converted during _wrap_conditions")


class BinaryExpr(Expr):
    """二元表达式基类"""

    __slots__ = (
        "negate",
        "left",
        "right",
        "priority",
        "cache_config",
        "right_val",
        "right_contexts",
        "left_val",
        "left_contexts",
        "always_true",
        "_cached_evaluate",
    )

    def __init__(self, left, right, negate=False):
        if not is_hashable(left, right):
            raise TypeError("Expression elements must be hashable")
        self.left, self.right, left_is_field = _adjust_field(left, right)

        self.negate = negate
        self.priority = self.left.priority if left_is_field else 0
        self.always_true = self.left.field.always_true if left_is_field else False
        self.cache_config = self.left.field.cache if left_is_field and self.left.field.cache else None
        if self.cache_config:
            self._cached_evaluate = async_cached(
                self.cache_config.cache,
                ignore=self.cache_config.ignore_func,
            )(self._evaluate_wrapper)

    async def evaluate(self, msg):
        if self.always_true:
            return True, []
        if self.cache_config:
            return await self._cached_evaluate(
                self.left,
                self.right,
                msg,
                cache_key=lambda *_: self.cache_config.key_func(self.__class__.__name__, self.right, msg),
            )
        result = await self._evaluate_wrapper(self.left, self.right, msg)
        self.right_val = self.right_contexts = self.left_val = self.left_contexts = None
        return result

    async def _evaluate_wrapper(self, left, right, msg):
        self.right_val, self.right_contexts = right, []

        # 覆盖逻辑
        if isinstance(left, FieldClause) and (result := left.field.overrides.get(self.right_val)) is not None:
            return result ^ self.negate, []

        self.left_val, self.left_contexts = (await left.evaluate(msg)) if isinstance(left, FieldClause) else (left, [])
        return await self._evaluate_logic(msg)

    @abstractmethod
    async def _evaluate_logic(self, msg):
        raise NotImplementedError


class BoolExpr(Expr):
    """布尔逻辑表达式基类"""

    __slots__ = ("clauses", "priority")

    def __init__(self, *clauses):
        clauses = tuple(c if isinstance(c, Expr) else RawCondition(c) for c in clauses)
        positives = sorted((x for x in clauses if x.priority > 0), key=lambda x: x.priority, reverse=True)
        zeros = [x for x in clauses if x.priority == 0]
        negatives = sorted((x for x in clauses if x.priority < 0), key=lambda x: x.priority, reverse=True)
        self.clauses: list[Expr | BinaryExpr] = positives + zeros + negatives
        self.priority = 0


# endregion
# region 运算表达式


class Equal(BinaryExpr):
    __slots__ = ()

    async def _evaluate_logic(self, msg) -> tuple[bool, list]:
        # 正则
        if isinstance(self.left, FieldClause) and isinstance(self.right_val, re.Pattern):
            if match := self.right_val.fullmatch(_strip_message_prefix(getattr(msg, "raw_message", ""), msg.self_id)):
                return True ^ self.negate, [match]
            return False ^ self.negate, []

        return (self.left_val == self.right_val) ^ self.negate, self.left_contexts + self.right_contexts


class NotEqual(Equal):
    __slots__ = ()

    def __init__(self, left, right):
        super().__init__(left, right, True)


class Contains(BinaryExpr):
    __slots__ = ()

    async def _evaluate_logic(self, _) -> tuple[bool, list]:
        return (self.left_val in self.right_val) ^ self.negate, self.left_contexts + self.right_contexts


class NotContains(Contains):
    __slots__ = ()

    def __init__(self, left, right):
        super().__init__(left, right, True)


# endregion
# region 逻辑表达式
class And(BoolExpr):
    __slots__ = ()

    async def evaluate(self, msg) -> tuple[bool, list]:
        contexts = []
        for clause in self.clauses:
            result, ctx = await clause.evaluate(msg)
            if not result:
                return False, []
            contexts.extend(ctx)
        return True, contexts


class Or(BoolExpr):
    __slots__ = ()

    async def evaluate(self, msg) -> tuple[bool, list]:
        for clause in self.clauses:
            result, ctx = await clause.evaluate(msg)
            if result:
                return True, ctx
        return False, []


class Not(Expr):
    __slots__ = ("clause", "priority")

    def __init__(self, clause):
        self.clause = clause if isinstance(clause, Expr) else RawCondition(clause)
        self.priority = clause.priority

    async def evaluate(self, msg) -> tuple[bool, list]:
        result, ctx = await self.clause.evaluate(msg)
        return not result, ctx


# endregion
# region 字段作用方法

# region 限速
LIMIT = cfg.limit


class MsgLimit(dbBase):
    __tablename__ = "message_limit"
    user_id = Column(Integer, primary_key=True)
    count = Column(Integer, default=1)
    last_time = Column(Float)


async def _check_rate_limit(msg: GroupMessage | PrivateMessage | NoticeMessage | Request):
    """被限速 => False，正常状态 => True"""
    if await _is_admin(msg):
        return True
    current_time = time()
    async with db_session_factory() as session:
        result = await session.execute(
            update(MsgLimit)
            .where((MsgLimit.user_id == msg.user_id) & (MsgLimit.last_time <= current_time - 60))
            .values(count=1, last_time=current_time)
            .returning(MsgLimit.count)
        )
        if result.scalar_one_or_none() is not None:
            await session.commit()
            return True

        result = await session.execute(
            update(MsgLimit)
            .where(MsgLimit.user_id == msg.user_id)
            .values(count=MsgLimit.count + 1, last_time=current_time)
            .returning(MsgLimit.count)
        )
        if (updated_count := result.scalar_one_or_none()) is not None:
            await session.commit()
            return updated_count <= LIMIT

        await session.execute(insert(MsgLimit).values(user_id=msg.user_id, last_time=current_time))
        await session.commit()
        return True


# endregion


async def _is_validated(msg: GroupMessage | PrivateMessage | NoticeMessage | Request):
    import modules.moderator.managing_member as mm

    async with db_session_factory() as session:
        result = await session.scalar(select(mm.Verify.is_validated).filter(mm.Verify.user_id == msg.user_id))
        return result is None or bool(result)


# region 消息处理


def _strip_message_prefix(msg: str, self_id: int):
    """去除消息前缀"""
    for prefix in (cfg.message_prefix, convert_text(cfg.message_prefix), f"[CQ:at,qq={self_id}]"):
        msg = msg.removeprefix(prefix).lstrip()
    return msg


def _has_message_prefix(msg: GroupMessage | PrivateMessage | NoticeMessage | Request):
    return any(
        msg.raw_message.startswith(prefix)
        for prefix in (cfg.message_prefix, convert_text(cfg.message_prefix), f"[CQ:at,qq={msg.self_id}]")
    )


# endregion


async def _is_admin(msg: GroupMessage | PrivateMessage | NoticeMessage | Request):
    from .api import is_admin

    return await is_admin(msg.group_id, msg.user_id)


# endregion
# region private
logger = getLogger(__name__)


def _wrap_conditions(conditions, msg_type):
    """包装原始条件"""
    is_message = msg_type == "message"
    message_wrapper = lambda c: Equal(PM.message, re.compile(c, re.I | re.M) if isinstance(c, str) else c)
    exp = None

    def convert_expr(expr):
        if isinstance(expr, (And, Or)):
            return expr.__class__(*(converted for c in expr.clauses if (converted := convert_expr(c)) is not None))
        elif isinstance(expr, Not):
            return None if (converted := convert_expr(expr.clause)) is None else Not(converted)
        elif isinstance(expr, BinaryExpr):
            if expr.left.name == "exp":
                nonlocal exp
                if exp is not None:
                    raise ValueError("Only one exp can exist in a single expression.")
                exp = (time() + expr.right) if expr.right < 1000000000 else expr.right
                return
            converted_left, converted_right = convert_expr(expr.left), convert_expr(expr.right)
            if converted_left is not None and converted_right is not None:
                return expr.__class__(converted_left, converted_right, expr.negate)
        elif isinstance(expr, RawCondition):
            return None if expr.value is None else message_wrapper(expr.value) if is_message else expr.value
        elif isinstance(expr, (str, re.Pattern)):
            return message_wrapper(expr) if is_message else expr
        return expr

    # 处理顶层条件
    processed = []
    root_strings = []
    for expr in conditions:
        if isinstance(converted := convert_expr(expr), str):
            root_strings.append(converted)
        else:
            processed.append(converted)

    # 特殊处理
    if not is_message and root_strings:
        if len(root_strings) > 2:
            raise ValueError(f"Too many string arguments. Expected at most 2, got {len(root_strings)}.")

        # [0] -> 类型，[1] -> 子类型
        if root_strings:
            processed.insert(0, Equal(getattr(PM, msg_type), root_strings[0]))
        if len(root_strings) == 2:
            processed.append(Equal(PM.sub_type, root_strings[1]))

    # 去重校验
    seen_fields = set()
    final_conditions = []
    for expr in processed:
        if expr is None:
            continue
        if isinstance(expr, Equal) and isinstance(expr.left, FieldClause):
            if expr.left.name in seen_fields:
                continue
            seen_fields.add(expr.left.name)
        final_conditions.append(expr)

    return final_conditions, exp


def _collect_used_fields(expr: Expr) -> frozenset[str]:
    used = []
    if isinstance(expr, FieldClause):
        used.append(expr.name)
    elif isinstance(expr, BoolExpr):
        for clause in expr.clauses:
            used.extend(_collect_used_fields(clause))
    elif isinstance(expr, Not):
        used.extend(_collect_used_fields(expr.clause))
    elif isinstance(expr, BinaryExpr):
        used.extend(_collect_used_fields(expr.left))
        used.extend(_collect_used_fields(expr.right))
    return used


def _validate_expr(expr):
    """验证表达式结构"""
    if isinstance(expr, And):
        unique_fields = set()
        for clause in expr.clauses:
            if isinstance(clause, Equal) and isinstance(clause.left, FieldClause) and clause.left.field.unique:
                if clause.left.name in unique_fields:
                    raise ValueError(f"Duplicate unique field {clause.left.name} in And clause")
                unique_fields.add(clause.left.name)
            _validate_expr(clause)
    elif isinstance(expr, Or):
        for clause in expr.clauses:
            _validate_expr(clause)  # 递归验证子句
    elif isinstance(expr, Not):
        _validate_expr(expr.clause)  # 验证被取反的子表达式
    elif isinstance(expr, BinaryExpr):
        _validate_expr(expr.left)
        _validate_expr(expr.right)


async def _get_field_value(field: FieldClause, msg: GroupMessage | PrivateMessage | NoticeMessage | Request):
    if not field.field.extractor:
        raise ValueError(f"Missing extractor for field {field.name}")
    return await async_run_func(field.field.extractor, msg)


def _adjust_field(left, right) -> tuple[FieldClause | Any, bool, FieldClause | Any]:
    if (left_is_field := isinstance(left, FieldClause)) and (right_is_field := isinstance(right, FieldClause)):
        raise TypeError("Comparison requires at least one FieldClause operand")

    return (
        left if left_is_field or not right_is_field else right,
        left if right_is_field else right,
        left_is_field or right_is_field,
    )


# region 缓存

match_cache = get_cache(MemLRUCache, maxsize=parse_size(cfg.get_config("match_cache", "64MB", "cache", "消息匹配缓存大小。")))
validated_cache = get_cache(
    MemLRUCache, maxsize=parse_size(cfg.get_config("validated_cache", "648KB", "cache", "已验证用户缓存大小。"))
)


@dataclass
class CacheConfig:
    """二元表达式评估结果缓存配置，用于字段属性

    Attributes:
        cache: 继承自 `cachetools.Cache` 的缓存器。
        key_func: 生成缓存键的方法，接收运算符的类名、表达式中第二个操作数和 `msg`。
        ignore_func: 决定是否缓存结果的函数，接收 `评估结果, left, right, msg`。

    """

    cache: Any
    key_func: Callable[[str, Any, GroupMessage | PrivateMessage | NoticeMessage | Request], Hashable] = (
        lambda operator, right, _: hashkey(operator, right)
    )
    ignore_func: Callable[[Any, FieldClause, Any, GroupMessage | PrivateMessage | NoticeMessage | Request], bool] = None


"""async def _hash_evaluate(msg, expr):
    extractors = set()
    results = []
    for field in PM.__fields__.values():
        if field.extractor not in extractors:
            results.append(await async_run_func(field.extractor, msg))
    return hashkey(expr, *results)"""


# endregion


# endregion
# region public


class PM(metaclass=ExprMeta):
    """条件字段定义

    Attributes:
        message: 限定 `raw_message`
        request: `request_type`
        notice: `notice_type`
        sub_type: `sub_type`

        group: 是否为群聊消息。默认限定为群聊消息。该字段与 `private` 冲突。
        private: 是否为私聊消息。该字段与 `group` 冲突。
        groups: `group_id` 默认限定 `.in_(cfg.action_groups)`。
        users: `user_id`。

        prefix: 消息前端是否为 `cfg.message_prefix` 或@机器人。
        validated: 消息发送者是否已通过 `moderator` 模块验证。默认限定通过验证的。
        limit: 消息发送者是否遵循全局限速。默认遵循。未限定 `message`、`request_type`、`notice_type` 和 `sub_type` 时务必声明 `PM.limit == False`。
        exp: 该表达式实例将在几秒钟后/何时优先销毁，一般用于一次性表达式。若传入的值小于10^9，将会被 `build_cond` 修正为与当前秒级时间戳累加。
        admin: 消息发送者是否是群管理员。
        super: 消息发送者是否 in `cfg.super`。
    """

    __fields__: dict[str, Field]

    # 基本匹配字段
    message = Field(
        re.Pattern,
        lambda msg: getattr(msg, "raw_message", None),
        priority=1,
        cache=CacheConfig(
            cache=match_cache, key_func=lambda operator, right, msg: hashkey(operator, right.pattern, msg.raw_message)
        ),
        unique=True,
    )
    request = Field(str, lambda msg: getattr(msg, "request_type", None), unique=True)
    notice = Field(str, lambda msg: getattr(msg, "notice_type", None), unique=True)
    sub_type = Field(str, lambda msg: getattr(msg, "sub_type", None), priority=2, unique=True)

    # 消息来源字段
    group = Field(bool, lambda msg: hasattr(msg, "group_id"), True)
    private = Field(bool, lambda msg: not hasattr(msg, "group_id"))
    groups = Field(int, lambda msg: getattr(msg, "group_id", None), op=lambda f: f.in_(cfg.action_groups))
    users = Field(int, lambda msg: msg.user_id, priority=998)

    # 功能控制字段
    prefix = Field(bool, _has_message_prefix, unique=True)
    admin = Field(bool, _is_admin, priority=-1)
    super = Field(bool, lambda msg: msg.user_id in cfg.super)
    validated = Field(
        bool,
        _is_validated,
        True,
        priority=-2,
        cache=CacheConfig(
            cache=validated_cache,
            key_func=lambda operator, right, msg: hashkey(operator, right, msg.user_id),
            ignore_func=lambda _, __, right, ___: not right,
        ),
    )
    limit = Field(bool, _check_rate_limit, True, overrides={False: True}, priority=-999)

    # 属性字段
    exp = Field(float, lambda _: True, priority=999, unique=True, always_true=True)


def modify_expr(expr, *conditions: BinaryExpr):
    """递归修改表达式中的字段"""

    def traversal(expr, override: BinaryExpr):
        if isinstance(expr, BoolExpr):
            return expr.__class__(*(traversal(c, override) for c in expr.clauses))
        elif isinstance(expr, Not):
            return Not(traversal(expr.clause, override))
        elif isinstance(expr, BinaryExpr):
            left, right, _ = _adjust_field(override.left, override.right)
            return expr.__class__(expr.left, right if expr.left.name == left.name else expr.right, expr.negate)
        return expr

    for override in conditions:
        return traversal(expr, override)


def build_cond(conditions: tuple[Expr], msg_type: str) -> Expr:
    """构建条件"""
    conditions, exp = _wrap_conditions(conditions, msg_type)
    used_field_names = frozenset(chain.from_iterable(_collect_used_fields(cond) for cond in conditions))
    default_clauses = [
        field.op(FieldClause(name, field))
        for name, field in PM.__fields__.items()
        if name not in used_field_names
        and field.op is not None
        and (name != "group" or "private" not in used_field_names)
        and (name != "private" or "group" not in used_field_names)
    ]
    _validate_expr(cond := And(*conditions, *default_clauses) if default_clauses else And(*conditions))
    cond.exp = exp
    return cond


# @async_cached(expr_cache, key=hash_evaluate)
async def evaluate(msg, expr: Expr | BoolExpr, destroy_callback: Callable[[], None] = lambda: None) -> tuple[bool, list]:
    """评估表达式入口"""
    if (exp := getattr(expr, "exp", None)) and exp <= time():
        return destroy_callback(), ()
    try:
        if (result := await expr.evaluate(msg))[0] and exp:
            destroy_callback()
        return result
    except Exception:
        logger.exception("Error evaluating expression:")
    return False, ()


# endregion
