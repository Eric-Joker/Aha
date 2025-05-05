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
from asyncio import get_event_loop, run_coroutine_threadsafe
from logging import Filter, getLogger
from multiprocessing import Queue
from threading import Thread

from tenacity import RetryCallState, retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from websockets.exceptions import WebSocketException

from config import cfg
from ncatbot.core import BotClient
from ncatbot.utils import config
from services.apscheduler import scheduler, scheduler_init
from services.database import db_engine, db_init
from utils import install_uvloop, process_clean, process_message, process_notice, process_queue, process_request, process_start

# ncatbot 配置
config.set_bot_uin(str(cfg.get_config("bot_qq", 114514, "ncatbot")))
config.set_root(str(cfg.get_config("super_user", 1919810, "ncatbot")))
config.set_ws_uri(cfg.get_config("napcat_ws", "ws://127.0.0.1:12345", "ncatbot"))
config.set_ws_token(cfg.get_config("napcat_token", "ciallo", "ncatbot"))
config.set_webui_uri(cfg.get_config("napcat_webui", "http://127.0.0.1:54321", "ncatbot"))
config.set_webui_token(cfg.get_config("webui_token", "ciallo", "ncatbot"))

bot = BotClient()


@bot.group_event()
async def on_group_message(msg):
    await process_message(msg)


@bot.private_event()
async def on_private_message(msg):
    await process_message(msg)


@bot.notice_event()
async def on_notice_message(msg):
    await process_notice(msg)


@bot.request_event()
async def on_request_message(msg):
    await process_request(msg)


# 处理来自 Fastapi 的请求
def queue_worker(queue: Queue, loop):
    while True:
        if not isinstance((data := queue.get()), tuple):
            break
        run_coroutine_threadsafe(process_queue(*data), loop)


def log_after_retry_network(retry_state: RetryCallState):
    getLogger(retry_state.fn.__qualname__).exception(
        f"Retry attempt {retry_state.attempt_number + 1} failed with exception:\n{str(retry_state.outcome.exception())}"
    )


retry_network = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(min=1, max=30),
    retry=retry_if_exception_type(WebSocketException),
    before_sleep=log_after_retry_network,
)


# ban 掉一些日志
class LogFilter(Filter):
    def filter(self, record):
        if "插件" in record.getMessage():
            return False
        return True


getLogger("Logger").addFilter(LogFilter())  # ncatbot 拿这个做日志命名空间是真的抽象
getLogger("PluginLoader").addFilter(LogFilter())


def run_bot(queue):
    async def init_services():
        await db_init()

        bot.api._http.post = retry_network(bot.api._http.post.__func__).__get__(
            bot.api._http, bot.api._http.__class__
        )  # 为 API 添加网络错误重试

        await scheduler.__aenter__()
        await scheduler.start_in_background()
        scheduler_init()

        await process_start()

        Thread(target=queue_worker, args=(queue, get_event_loop()), daemon=True).start()

    async def clean_services():
        task = get_event_loop().run_in_executor(None, cfg.save)
        await process_clean()

        setattr(scheduler, "_services_task_group", None)
        await scheduler.stop()

        await db_engine.dispose()
        await task

    import modules
    import utils.api

    cfg.finalize_initialization()
    install_uvloop()

    bot.add_startup_handler(init_services)
    bot.add_shutdown_handler(clean_services)
    bot.run()
