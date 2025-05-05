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
import datetime
import time
from decimal import Decimal
from traceback import format_exc

from openai import APIError, AsyncOpenAI
from openai.types.chat import ChatCompletion
from sqlalchemy import delete, insert, select
from transformers import AutoTokenizer
from transformers.tokenization_utils import PreTrainedTokenizer

from config import cfg
from services.database import db_session_factory
from services.ncatbot import bot
from utils import round_decimal

from ..money import adjust_money, decimal_to_str, inquiry_money
from .database import History

client = AsyncOpenAI(
    api_key=cfg.get_config("api_key", "abcdefg"), base_url=cfg.get_config("ai_api", "https://api.deepseek.com")
)
PRICE = Decimal(cfg.get_config("price", "0.02", comment="每 token 消耗的点数。"))
MAX_HISTORY_LENGTH = cfg.get_config("max_length", 20, comment="每个会话最大历史记录数，必须大于2。")
PROMPT = cfg.get_config(
    "prompt",
    "你是猫娘Neko，句尾常加'喵~'，喜欢颜文字和emoji，唯一主人是群主%s。回复与思考尽可能简短，拒绝回复长内容。",
)
MASTER = cfg.get_config("master", "Er1c", comment="嵌在提示词里的 %s。")
MODEL_MAP = {"V3": "deepseek-chat", "R1": "deepseek-reasoner"}
HUGGINGFACE_MAP = {"deepseek-chat": "deepseek-ai/DeepSeek-V3-0324", "deepseek-reasoner": "deepseek-ai/DeepSeek-R1"}


# 异步查询对话历史
async def get_histories(user_id: int, model: str):
    async with db_session_factory() as session:
        result = await session.execute(
            select(History.role, History.content)
            .where(History.user_id == user_id)  #  and History.model == model
            .order_by(History.time.asc())
        )
    return [dict(row) for row in result.mappings()]


# 异步存储对话历史
async def save_history(user_id: int, model: str, role: str, content: str):
    async with db_session_factory() as session:
        # 获取保留阈值的时间点
        time_threshold_subquery = (
            select(History.time)
            .where(History.user_id == user_id)
            .order_by(History.time.desc())
            .offset(MAX_HISTORY_LENGTH - 2)
            .limit(1)
            .scalar_subquery()
        )

        # 删除早于阈值且非system的消息
        await session.execute(
            delete(History)
            .where(History.user_id == user_id)
            .where(History.time < time_threshold_subquery)
            .where(History.role != "system")
        )

        # 插入新消息
        await session.execute(
            insert(History).values(time=time.time_ns(), user_id=user_id, model=model, role=role, content=content)
        )
        await session.commit()


# 统计token
def count_tokens(tokenizer: PreTrainedTokenizer, context):
    return len(tokenizer.encode(context, add_special_tokens=False))


def calculate_price(now: datetime.time, tokens, model, out, hit=False):
    return (
        Decimal(str(tokens))
        * (2 if model == "deepseek-reasoner" else 1)
        / (1 if out else 4)
        / (2 if hit else 1)
        / ((4 if model == "deepseek-reasoner" else 2) if datetime.time(0, 30) <= now < datetime.time(8, 30) else 1)
        * PRICE
    )


# 主对话处理函数：调用DeepSeek API进行对话
async def deepseek(model, content, temper, user_id, user_name):
    now = datetime.datetime.now().time()
    prompt = f"{PROMPT % MASTER}现在{user_name}与你对话{"" if user_id in cfg.super else f"不是{MASTER}"}"
    # 如果是第一次对话，先插入系统提示
    async with db_session_factory() as session:
        if is_first := not (await session.scalar(select(select(History).filter(History.user_id == user_id).exists()))):
            await session.execute(
                insert(History).values(time=time.time_ns(), user_id=user_id, model=model, role="system", content=prompt)
            )
        await session.commit()
    try:
        # 计算基本钱
        out_price = 0
        tokenizer = AutoTokenizer.from_pretrained(HUGGINGFACE_MAP[model])
        if is_first:
            price = calculate_price(now, count_tokens(tokenizer, prompt) + count_tokens(tokenizer, content), model, False)
        else:
            histories = await get_histories(user_id, model)
            price = calculate_price(
                now, sum(count_tokens(tokenizer, i["content"]) for i in histories), model, False, True
            ) + calculate_price(now, count_tokens(tokenizer, content), model, False)

        # 第一次扣钱
        if (user_point := await inquiry_money(user_id)) <= price:
            return f"余额不足，至少需要{decimal_to_str(price)}点能量。你当前有{decimal_to_str(user_point)}点。", 0
        await adjust_money(user_id, -price)

        await save_history(user_id, model, "user", content)  # 添加用户消息到历史
        chat: ChatCompletion = await client.chat.completions.create(  # 调用DeepSeek API（关闭流式传输）
            model=model, messages=await get_histories(user_id, model), stream=False, max_tokens=4500, temperature=temper
        )

        # 第二次扣钱
        out_price = (
            calculate_price(now, chat.usage.completion_tokens, model, True)
            + calculate_price(now, chat.usage.model_extra["prompt_cache_hit_tokens"], model, False, True)
            + calculate_price(now, chat.usage.model_extra["prompt_cache_miss_tokens"], model, False)
        )
        await adjust_money(user_id, -out_price + price)

        await save_history(user_id, model, "assistant", (response := chat.choices[0].message.content))  # 更新历史记录
        return response, round_decimal(out_price)
    except APIError as e:  # 处理API错误
        error_messages = {
            400: "请求格式错误，请检查输入内容。",
            401: "API密钥认证失败，请联系管理员。",
            402: "账号余额不足，请及时充值。",
            422: "请求参数错误，请检查输入内容。",
            429: "请求过于频繁，请稍后再试。",
            500: "服务器内部故障，请稍后再试。",
            503: "服务器繁忙，请稍后再试。",
        }  # 预定义错误消息映射
        error_msg = error_messages.get(e.status_code, "服务暂时不可用，请稍后再试。")
        await bot.api.post_private_msg(cfg.super[0], f"{user_id} 请求 DeepSeek 时报错：\n{error_msg}")
        await adjust_money(user_id, price)
        return "出错啦，已通知群主~ 能量已返还", 0
    except Exception as e:
        await bot.api.post_private_msg(cfg.super[0], f"{user_id} 请求 DeepSeek 时报错：\n{format_exc()}")
        await adjust_money(user_id, price)
        return "出错啦，已通知群主~ 能量已返还", 0


# 重置对话历史记录
async def deepseek_reset(user_id, model):
    async with db_session_factory() as session:
        await session.execute(
            delete(History).where(History.user_id == user_id, History.model == MODEL_MAP[model] if model else True)
        )
        await session.commit()
