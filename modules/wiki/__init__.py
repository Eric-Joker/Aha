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
from asyncio import create_task
from base64 import b64encode
from traceback import format_exc

from aiohttp import ClientSession
from ncatbot.core import Image, MessageChain
from ncatbot.core.message import GroupMessage
from regex import Match

from config import cfg
from services.ncatbot import bot
from utils import PM, And, capture_element, message_handlers, on_message

from .client import MediaWikiClient

WIKI_MAP = {
    "wiki": "https://zh.minecraft.wiki",
    "enwiki": "https://minecraft.wiki",
    "devwiki": "https://wiki.mcbe-dev.net/w",
}


@on_message(And("wiki", PM.prefix == True), registered_menu={"wiki": "查询 Wiki 词条"})
async def wk(msg: GroupMessage, _):
    await bot.api.post_group_msg(
        msg.group_id, "Wiki：\n[wiki/enwiki/devwiki 词条] - 中文MCwiki/英文MCwiki/基岩开发wiki", reply=msg.message_id
    )


async def send_wiki_response(group_id, result, reply_id):
    task = create_task(capture_element(result[1], "div.notaninfobox"))
    await bot.api.post_group_msg(group_id, "\n".join(result))
    if img := await task:
        await bot.api.post_group_msg(group_id, rtf=MessageChain([Image(f"base64://{b64encode(img).decode()}")]))


async def handle_wiki_error(group_id, reply_id):
    create_task(bot.api.post_private_msg(cfg.super[0], f"请求 wiki 时报错：\n{format_exc()}"))
    await bot.api.post_group_msg(group_id, "出错了。", reply=reply_id)


@on_message(r"(\S*wiki)\s*([\s\S]+)")
async def fetch(msg: GroupMessage, match: Match):
    if not (url := WIKI_MAP.get(match.group(1))):
        return

    await bot.api.send_poke(msg.user_id, msg.group_id)

    try:
        async with ClientSession() as session:
            if result := await (client := MediaWikiClient(session, url)).fetch_intro(term := match.group(2).strip()):
                await send_wiki_response(msg.group_id, result, msg.message_id)
            else:
                similar = await client.search_and_cache_results(msg.user_id, term)
                message_handlers.add(r"(\d+)", PM.users == msg.user_id, PM.exp == 300, callback=reget)
                await bot.api.post_group_msg(
                    msg.group_id,
                    f"找不到该词条{f"，相似的有：\n{"\n".join(f"{i+1}. {v}" for i, v in enumerate(similar))}\n五分钟内发送序号即可获取" if similar else "。"}",
                    reply=msg.message_id,
                )
    except Exception:
        await handle_wiki_error(msg.group_id, msg.message_id)


async def reget(msg: GroupMessage, match: Match):
    create_task(bot.api.send_poke(msg.user_id, msg.group_id))
    try:
        async with ClientSession() as session:
            if result := await MediaWikiClient(session).get_cached_intro(msg.user_id, int(match.group(1)) - 1):
                await send_wiki_response(msg.group_id, result, msg.message_id)
    except Exception:
        await handle_wiki_error(msg.group_id, msg.message_id)
