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
import signal
import sys
from asyncio import run
from codecs import getwriter
from multiprocessing import Process, Queue, freeze_support

from config.base import cfg

sys.stdout = getwriter("utf-8")(sys.stdout.detach())


def handle_sigterm(*_):
    raise SystemExit(1)


if __name__ == "__main__":
    import fastapi_modules
    import modules
    from services.database import db_init
    from services.ncatbot import run_bot

    run(db_init())

    # 启动 FastAPI 服务
    task_queue = Queue()
    if cfg.enable_fastapi:
        from services.fastapi import run_fastapi

        if sys.platform == "win32":
            freeze_support()
        api_process = Process(target=run_fastapi, args=[task_queue], daemon=True)
        api_process.start()

    # 启动 NcatBot
    signal.signal(signal.SIGTERM, handle_sigterm)
    run_bot(task_queue)
    if cfg.enable_fastapi:
        api_process.join()
