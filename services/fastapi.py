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
from multiprocessing import Queue

from fastapi import FastAPI
from uvicorn import run

from utils import install_uvloop

app = FastAPI()
task_queue: Queue = None


def run_fastapi(queue):
    global task_queue
    task_queue = queue
    import fastapi_modules

    install_uvloop()
    run(app, host="0.0.0.0", port=6550)
