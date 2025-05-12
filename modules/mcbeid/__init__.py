from asyncio import create_task
from traceback import format_exc

import regex as re
from aiohttp import ClientSession
from tenacity import retry, stop_after_attempt, wait_exponential

from config import cfg
from ncatbot.core import GroupMessage
from services.ncatbot import bot
from utils import PM, And, on_message

SEARCH_LIMIT = 3


@on_message(And("beid", PM.prefix == True), registered_menu={"beid": "查询 MCBE 的 ID 表。"})
async def wk(msg: GroupMessage, _):
    await bot.api.post_group_msg(msg.group_id, "BEID：\n[beid 词条]", reply=msg.message_id)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5), reraise=True)
async def _fetch_api(query):
    async with ClientSession() as session:
        async with session.get(
            "https://ca.projectxero.top/idlist/search", params={"q": query, "limit": SEARCH_LIMIT + 1}
        ) as resp:
            resp.raise_for_status()
            return await resp.json()


@on_message(r"beid\s*(\S+)")
async def mcbeid(msg: GroupMessage, match: re.Match):
    try:
        data = (await _fetch_api(match.group(1).strip()))["data"]
    except Exception:
        create_task(bot.api.post_private_msg(cfg.super[0], f"请求 API 时报错：\n{format_exc()}"))
        return await bot.api.post_group_msg(msg.group_id, "出错了。", reply=msg.message_id)
    if result := data["result"]:
        plain_texts = [f'{item["enumName"]}：{item["key"]} -> {item["value"].split("\n")[0]}' for item in result[:SEARCH_LIMIT]]
        if len(result) > SEARCH_LIMIT:
            plain_texts.append(f"\n查看更多：https://ca.projectxero.top/idlist/{data["hash"]}")
        return await bot.api.post_group_msg(msg.group_id, "\n".join(plain_texts), reply=msg.message_id)
    await bot.api.post_group_msg(msg.group_id, "没有找到结果。", reply=msg.message_id)
