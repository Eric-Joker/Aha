from asyncio import Task

from aiologic import Event

from utils.aio import AsyncLoopExecutor

main_task: Task = None
all_ready = Event()
async_loop_executor: AsyncLoopExecutor = None
base64_buffer = None
def_lang = None
need_reboot = False
