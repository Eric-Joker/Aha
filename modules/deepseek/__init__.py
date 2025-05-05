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
from regex import Match

from ncatbot.core.message import GroupMessage
from services.ncatbot import bot
from utils import PM, on_message, Or
from utils.api import get_card_by_msg

from .ds import MODEL_MAP, deepseek, deepseek_reset


@on_message(Or("deepseek", "ds") & (PM.prefix == True), registered_menu={"deepseek": "和猫娘 Neko 聊天"})  # ~ds
async def ds(msg: GroupMessage, _):
    await bot.api.post_group_msg(
        msg.group_id,
        "Deepseek：\n[ds/deepseek v3/r1 (温度0-2) 消息]\n[ds/deepseek 重置(历史) (v3/r1)]\n\n群主是穷逼 定价不透明\nr1更贵 凌晨便宜\n\n温度建议：\n数学编程 - 0.0\n数据分析 - 1.0\n对话翻译 - 1.3\n创意写作 - 1.5\n\n示例：\ndsv3 摸摸\ndsr1 0 证明哥德巴赫猜想",
        reply=msg.message_id,
    )


@on_message(r"d(?:eep)?s(?:eek)?\s*(v3|r1)\s+(?:([01](?:\.[0-9]+)?|2(?:\.0))\s+)?([\s\S]+)")  # dsv3 text
async def create(msg: GroupMessage, match: Match):
    await bot.api.send_poke(msg.user_id, msg.group_id)
    temper = round(float(temper), 1) if (temper := match.group(2)) else 1
    model = MODEL_MAP[m.upper() if (m := match.group(1)) else "V3"]
    response, price = await deepseek(model, match.group(3).strip(), temper, msg.user_id, await get_card_by_msg(msg))
    await bot.api.post_group_msg(msg.group_id, response + (f"\n\n本次消耗能量{price}点" if price else ""), reply=msg.message_id)


@on_message(r"d(?:eep)?s(?:eek)?\s*重置(?:历史)?\s*(v3|r1|)\s*$")  # ds重置r1
async def reset(msg: GroupMessage, match: Match):
    await deepseek_reset(msg.user_id, (model := match.group(1).upper()))
    await bot.api.post_group_msg(msg.group_id, f"已重置{model or '所有'}模型历史记录", reply=msg.message_id)
