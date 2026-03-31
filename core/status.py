from asyncio import Event, Task

main_task: Task = None
all_ready = Event()
base64_buffer = None
def_lang = None
need_reboot = False