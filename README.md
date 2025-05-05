<div align="center">

[![](https://img.shields.io/badge/license-GPLv3-blue)](https://github.com/Eric-Joker/Aha/blob/main/LICENSE)
[![](https://img.shields.io/badge/python-3.12-yellow)](https://www.python.org)

[🛠安装](#安装) |
[📖使用](#使用) |
[💡议题](https://github.com/Eric-Joker/Aha/issues)

</div>

# Aha

Aha 目前是一个基于但不止基于 [ncatbot](https://github.com/liyihao1110/ncatbot) 的聊天机器人框架。
本项目开发时的宗旨是不重复造轮子(但会造扳手)，直接使用成熟方案。

- 嗯？ncatbot 本身不就是一个框架吗？
- 所以本项目还基于了 [apscheduler(4.0)](https://github.com/agronholm/apscheduler)、[FastAPI](https://github.com/fastapi/fastapi)、[SQLAlchemy](https://github.com/sqlalchemy/sqlalchemy) 等依赖，以扩充 ncatbot 原不具有的特性，提高插件开发的自由度。

目前本项目十分的不成熟，基本只供我自用，未提供懒人设施，若有需要可以提 issue。

## 都造了什么轮子？

- 基于 逻辑表达式 的词条匹配系统
  ```python
  from utils import PM, Or

  # 消息完全匹配正则且(用户在集合里或群聊为666)。
  (PM.message == "正则表达式"或re.Pattern) & (PM.users.in_({114514, 1919810}) | (PM.groups == 666))
  # 直接创建逻辑运算类实例时，可以省略 PM.message 或 PM.notice/request_type、PM.sub_type。
  Or("正则表达式", PM.prefix == True)

  # 多个表达式之间默认为并列关系
  @on_message(PM.super == True, PM.admin == True) # 要求同时为超级用户和管理员
  ```
- 封装部分 API，模拟正常客户端操作，防止将来被滥封。(在 utils.api 中)
- 将一些 API 返回值解析为对象，以简化取用。(在 utils.api 中)
- 为 ncatbot API 网络请求添加自动重试以照顾远程调试需求。
- 对部分逻辑实施了缓存(基于内存占用的 LRU、定时清空)，以便在大体量下加快响应速度。
- 中文时间段描述解析为秒数  
  ```python
  from utils import str2sec

  str2sec("1年3个月") # 返回 39446190
  str2sec("1,2,3") # 相同分隔符自动解析，返回 3723
  ```
- 统一配置系统
  ```python
  # modules/deepseek/ds.py
  from config import cfg

  MAX_HISTORY_LENGTH = cfg.get_config("max_length", 20, comment="每个会话最大历史记录数，必须大于2。")
  cfg.max_length # 以后可如此获取配置
  ```
  会自动生成↓
  ```yaml
  modules.deepseek:
    # 每个会话最大历史记录数，必须大于2。
    max_length: 20
  ```
- 基于 FastAPI 的被动触发特性
  ```python
  # fastapi_modules/test/__init__.py
  @app.post("/test")
  async def abc(body)
    task_queue.put(("test", body)) 

  # modules/test/__init__.py
  @queue_handler("test")
  async def xyz(body)
  ```
- 基于 APScheduler 毫秒级精度的定时调度
  ```python
  from services.apscheduler import scheduler

  await scheduler.add_schedule(process, TimeTrigger(sec), args=(msg,), metadata={"user_id": msg.user_id, "tag": "trigger"}) # TimeTrigger 由本项目实现，以便于实现延时调度。
  ```
- 基于 SQLAlchemy 的直接操作持久化数据实现
  ```python
  # modules/money/database.py
  from sqlalchemy import Column, Integer, Numeric
  from services.database import dbBase

  class Money(dbBase):
      __tablename__ = "money"
      user_id = Column(Integer, primary_key=True)
      points = Column(Numeric, default=0)

  # modules/money/__init__.py
  from sqlalchemy import func, insert, select, update
  from services.database import db_session_factory

  async def adjust_money(user_id, points: int | Decimal):
      async with db_session_factory() as session:
          result = await session.execute(update(Money).where(Money.user_id == user_id).values(points=Money.points + points))
          if result.rowcount == 0:
              await session.execute(insert(Money).values(user_id=user_id, points=points))
          await session.commit()
  ```
- 等等。
  
## 安装

您的设备上需要装有 Python 3.12 或更高版本。

首先，下载由源代码打包的压缩包并解压或使用 Git 克隆仓库：
```sh
git clone https://github.com/Eric-Joker/Aha.git
cd Aha
```
然后，使用 pip 安装依赖：
```sh
pip install -r requirements.txt
```
目前未实现模块依赖处理特性。

## 使用

本项目的配置系统基于环境变量 `BOT_ENV` 区分配置文件，采用的文件为 `config.BOT_ENV.yml`，默认为  `dev`。
```sh
python qqbot.py
```
启动后会引用所有模块，届时模块调用 `get_config` 进行配置注册。如果有新增配置会写入文件并终止运行，修改配置后可再次启动。

在 Linux 生产环境时，可以通过项目提供的 ./run.sh 启动项目。

本项目尚未提供非开发者友好使用方案。
