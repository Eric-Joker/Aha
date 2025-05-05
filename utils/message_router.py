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
from asyncio import Lock, create_task
from collections import deque
from copy import deepcopy
from functools import wraps
from sys import exit
from time import time
from typing import Callable

from ncatbot.core.message import GroupMessage, PrivateMessage
from ncatbot.core.notice import NoticeMessage
from ncatbot.core.request import Request

from .expr import PM, Expr, build_cond, evaluate
from .misc import async_run_func

message_handlers: list[tuple[Expr, Callable]] = []
queue_handlers: dict[str, Callable] = {}
notice_handlers: list[tuple[Expr, Callable]] = []
request_handlers: list[tuple[Expr, Callable]] = []
start_handlers: list[Callable] = []
clean_handlers: list[Callable] = []
menu_commands: list[tuple[str, Expr, str | None]] = []


def on_message(*conditions: Expr, registered_menu: dict[str, str | None] = {}):
    """消息处理装饰器
    - 被装饰的函数必须是异步协程（`async def`）
    - func(GroupMessage | PrivateMessage, re.Match)

    Args:
    registered_menu: 将 `key` 注册进 `菜单` 词条，如果 `value` 有值，则作为说明。
    """

    def decorator(func):
        expr = build_cond(conditions, "message")

        # 注册菜单
        if registered_menu:
            for k, v in registered_menu.items():
                menu_commands.append((k, expr.modify(PM.limit == False), v))
        message_handlers.append((expr, func))
        return func

    return decorator


def queue_handler(key):
    """FastAPI 请求处理装饰器
    - 被装饰的函数必须是异步协程（`async def`）
    - func(data)

    Args:
        key: 区分调用函数的特征id

    """

    def decorator(func):
        queue_handlers[key] = func
        return func

    return decorator


def on_notice(*conditions: Expr):
    def decorator(func):
        notice_handlers.append((build_cond(conditions, "notice"), func))
        return func

    return decorator


def on_request(*conditions: Expr):
    def decorator(func):
        request_handlers.append((build_cond(conditions, "request"), func))
        return func

    return decorator


def on_start(func):
    start_handlers.append(func)
    return func


def on_shutup(func):
    clean_handlers.append(func)
    return func


async def process_message(msg: GroupMessage | PrivateMessage, force_trigger=False):
    from config import cfg

    truly_msg = deepcopy(msg)

    # 处理消息前缀
    truly_msg.raw_message = msg.raw_message.removeprefix(cfg.message_prefix).removeprefix(f"[CQ:at,qq={msg.self_id}]").lstrip()

    if msg.message:
        if is_at := msg.message[0]["data"].get("qq") == str(msg.self_id):
            del truly_msg.message[0]
        if (text_data := truly_msg.message[0].get("data")) and (text := text_data.get("text")) is not None:
            if is_at:
                text_data["text"] = text.lstrip().removeprefix(cfg.message_prefix)

    # 评估处理逻辑
    for expr, func in message_handlers:
        if force_trigger:
            expr = expr.modify(PM.prefix == False)

        result, context = await evaluate(msg, expr)
        if result:
            create_task(func(truly_msg, context[0] if context else None))


# 防止腾讯服务器抽风
def group_increase_limit(func):
    from config import cfg

    lock = Lock()
    times = deque()

    @wraps(func)
    async def wrapper(msg: NoticeMessage, *args, **kwargs):
        if msg.notice_type == "group_increase" and msg.group_id in cfg.action_groups:
            nonlocal times
            async with lock:
                now = time()
                while times and times[0] < now - 60:
                    times.popleft()
                if len(times) >= 5:
                    exit()
                times.append(now)
        return await func(msg, *args, **kwargs)

    return wrapper


@group_increase_limit
async def process_notice(msg: NoticeMessage):
    for expr, func in notice_handlers:
        if (await evaluate(msg, expr))[0]:
            create_task(func(msg))


async def process_request(msg: Request):
    for expr, func in request_handlers:
        if (await evaluate(msg, expr))[0]:
            create_task(func(msg))


async def process_start():
    for t in start_handlers:
        await async_run_func(t)


async def process_clean():
    for t in clean_handlers:
        await async_run_func(t)


async def process_queue(key, value):
    create_task(queue_handlers.get(key, lambda _: None)(value))
