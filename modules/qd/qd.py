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
import random
from datetime import datetime, timedelta

from sqlalchemy import insert

from config import cfg
from services.database import db_session_factory
from utils import round_decimal

from ..money import adjust_money, decimal_to_str, inquiry_money
from .database import UserSign

POINT_ITEMS = ((1, 18), (2, 28), (3, 35), (4, 12), (5, 5), (6, 2), (10, 1))  # (点数, 权重)
RANDOM_EVENTS = (
    {
        "text": ("发现能量晶簇！", "量子泡沫共振效应！", "捕获游离光子！", "时空折叠增益！", "检测到宇宙微波背景辐射异常！"),
        "points": 1,
    },
    {"text": ("遭遇时空湍流！", "反物质侵蚀！", "维度塌缩损耗！", "观测者效应干扰！", "遭遇熵增不可逆过程！"), "points": -1},
)
EVENT_PROB = cfg.get_config("event_prob", 0.05, comment="随机事件总触发概率。")
STREAK_BONUS_CYCLE = cfg.get_config("streak_cycle", 7, comment="连续签到周期。")
STREAK_BONUS_STAGES = cfg.get_config("streak_stages", 6, comment="固定周期次数。")
STREAK_BONUS_MAX = cfg.get_config("streak_max", 3, comment="固定周期奖励上限。")
STREAK_BONUS_RANGE = cfg.get_config("streak_range", (5, 10), comment="随机周期范围。")
STREAK_BONUS_PONITS = cfg.get_config("streak_points", (1, 15), comment="随机周期奖励范围。")


# 随机算法
def weighted_choice(items):
    rand = random.uniform(0, sum(w for _, w in items))
    cumulative = 0
    for value, weight in items:
        cumulative += weight
        if rand < cumulative:
            return value
    return items[-1][0]


# 连续签到奖励算法
def calculate_streak_bonus(user: UserSign, now: datetime):
    user.continuous_days = (
        user.continuous_days + 1 if user.last_sign and (now.date() - user.last_sign.date()) == timedelta(days=1) else 1
    )
    if user.streak_stage < STREAK_BONUS_STAGES:
        if user.continuous_days >= STREAK_BONUS_CYCLE * (user.streak_stage + 1):
            user.streak_stage += 1
            user.last_bonus_date = now
            return (
                (bonus := min(STREAK_BONUS_MAX, user.streak_stage)),  # 奖励点数
                f"🌟 连续观测奖励 +{bonus}（下次需{STREAK_BONUS_CYCLE if user.streak_stage < STREAK_BONUS_STAGES else f"{STREAK_BONUS_RANGE[0]}-{STREAK_BONUS_RANGE[1]}"}天）",
            )
    else:
        if (now - user.last_bonus_date).days >= random.randint(*STREAK_BONUS_RANGE):
            user.last_bonus_date = now
            return (bonus := random.randint(*STREAK_BONUS_PONITS)), f"💥 观测暴击！+{bonus} 点随机能量波动"
    return 0, None


async def sign(user_id, nickname):
    now = datetime.now()
    async with db_session_factory() as session:
        if not (user := await session.get(UserSign, user_id)):
            result = await session.execute(
                insert(UserSign).values(user_id=user_id, last_sign=None, last_bonus_date=None).returning(UserSign)
            )
            user = result.scalar_one()

        # 冷却检查
        if user.last_sign and user.last_sign >= (today_0am := now.replace(hour=0, minute=0, second=0, microsecond=0)):
            remaining_seconds = (today_0am + timedelta(days=1) - now).total_seconds()
            hours = int(remaining_seconds // 3600)
            minutes = int((remaining_seconds % 3600) // 60)
            await session.commit()
            return [f"⏳ 时空稳定协议生效中（剩余{hours}小时{minutes}分钟）"]

        # 基础积分
        points = (base_points := weighted_choice(POINT_ITEMS))
        response = [
            f"📅 {nickname} 签到成功：",
            f"- 获得能量：{base_points}点",
        ]

        # 连续签到
        points += (bonus := calculate_streak_bonus(user, now))[0]
        user.last_sign = now
        response.append(bonus[1])

        # 随机事件
        if random.random() < EVENT_PROB:
            points += (event_points := (event_type := random.choice(RANDOM_EVENTS))["points"])
            response.append(f"⚡ {random.choice(event_type['text'])}能量{event_points:+}")

        # 更新数据
        if len(tuple(x for x in response if x)) > 2:
            response.append(f"- 累计总量：{points}点")
        response.extend(
            [
                f"- 连续观测：{user.continuous_days}天",
                f"- 当前持有：{decimal_to_str(round_decimal((await inquiry_money(user_id)) + points))}点",
            ]
        )
        await session.commit()
    await adjust_money(user_id, points)

    return response
