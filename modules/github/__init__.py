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
from traceback import format_exc

from asyncio import create_task
from aiohttp import ClientSession
from regex import Match

from config import cfg
from ncatbot.core.message import GroupMessage
from services.ncatbot import bot
from utils import PM, And, on_message

from .client import GithubClient, Repository

SHORTCUT = cfg.get_config("github_shortcut", {"aha": "Eric-Joker/Aha"})


@on_message(And("github", PM.prefix == True), registered_menu={"github": "查询 Github 仓库/用户信息"})
async def gh(msg: GroupMessage, _):
    await bot.api.post_group_msg(
        msg.group_id, "Github：\n[gh/github (用户名/)仓库名] - 查询/搜索仓库\n[gu 用户名]", reply=msg.message_id
    )


async def send_repo_response(group_id, result: Repository, reply_id):
    await bot.api.post_group_msg(
        group_id,
        (
            f"📦 仓库: {result.name}\n"
            f"🔗 链接: {result.html_url}\n"
            f"📝 简介: {result.description or '暂无描述'}\n"
            f"🌐 语言: {result.language or '未指定'}\n"
            f"⭐ {result.stars} | 🍴 {result.forks} | 👀 {result.watchers}\n"
            f"📜 证书: {(result.license.name if result.license else None) or '无'}\n"
            f"⏰ 创建于: {result.created_at} | 更新于: {result.updated_at}"
        ),
        reply=reply_id,
    )


async def handle_error(group_id, reply_id):
    create_task(bot.api.post_private_msg(cfg.super[0], f"请求 Github 时报错：\n{format_exc()}"))
    await bot.api.post_group_msg(group_id, "出错了。", reply=reply_id)


@on_message(r"(?:gh|github)\s*([\s\S]+)")
async def fetch_repo(msg: GroupMessage, match: Match):
    await bot.api.send_poke(msg.user_id, msg.group_id)

    is_repo = "/" in (term := SHORTCUT.get((term := match.group(1).strip()).lower()) or term)
    try:
        async with ClientSession() as session:
            client = GithubClient(session)
            if is_repo and (result := await client.get_repo(term)):
                await send_repo_response(msg.group_id, result, msg.message_id)
            else:
                similar = await client.cache_search(msg.user_id, term)
                await bot.api.post_group_msg(
                    msg.group_id,
                    f"{"找不到该仓库。" if is_repo else ""}{f"相似的有：\n{"\n".join(f"{i+1}. {v}" for i, v in enumerate(similar))}\n五分钟内发送序号即可获取" if similar else ""}",
                    reply=msg.message_id,
                )
    except Exception:
        await handle_error(msg.group_id, msg.message_id)


@on_message(r"gu\s*([\s\S]+)")
async def fetch_gh_user(msg: GroupMessage, match: Match):
    await bot.api.send_poke(msg.user_id, msg.group_id)
    try:
        async with ClientSession() as session:
            await bot.api.post_group_msg(
                msg.group_id,
                (
                    (
                        f"👤 用户: {result.login}\n"
                        f"🔗 链接: {result.html_url}\n"
                        f"🏷️ 类型: {result.type}\n"
                        f"❤️ 关注: {result.following} | 🕴️ 粉丝: {result.followers}\n"
                        f"📂 仓库: {result.public_repos} | 📝 Gists: {result.public_gists}\n"
                        f"⏰ 创建于: {result.created_at} | 活跃于: {result.updated_at}"
                    )
                    if (result := await GithubClient(session).get_user(match.group(1).strip()))
                    else "未找到该用户。"
                ),
                reply=msg.message_id,
            )
    except Exception:
        await handle_error(msg.group_id, msg.message_id)


@on_message(r"(\d+)", PM.limit == False)
async def reget(msg: GroupMessage, match: Match):
    try:
        async with ClientSession() as session:
            if result := await GithubClient(session).get_cached_repo(msg.user_id, int(match.group(1)) - 1):
                await send_repo_response(msg.group_id, result, msg.message_id)
    except Exception:
        await handle_error(msg.group_id, msg.message_id)
