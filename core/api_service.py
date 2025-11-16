from asyncio import CancelledError, Event, Future, create_task, gather, get_running_loop, sleep
from collections import defaultdict
from collections.abc import Mapping
from contextlib import suppress
from copy import deepcopy
from logging import getLogger
from multiprocessing import Pipe, Process
from secrets import token_hex
from threading import Thread
from weakref import WeakValueDictionary

from apscheduler.triggers.calendarinterval import CalendarIntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from attrs import define, field
from orjson import dumps
from pydantic import BaseModel
from xxhash import xxh3_64

from bots import BaseBot, api_process
from models.api import LifecycleSubType, MetaEventType, NoticeEventType, RequestEventType, RequestSubType
from models.core import APSTriggerType, EventCategory, ServiceType
from services.apscheduler import TimeTrigger, scheduler
from utils.aio import AsyncConnection, run_with_uvloop
from utils.typekit import commented2basic, parse_size

from .bot_register import get_bot_class
from .cache import Cache, CronMemLRUCache, FIFOCache, hashkey
from .config import cfg
from .deduplicator import Deduplicator
from .i18n import _
from .log import log_config
from .router import process_external, process_message, process_meta, process_notice, process_request

bots: dict[int, BotInstance | None] = {}
platform_bot_map: dict[str, list] = defaultdict(list)
deduplicators: dict[str, Deduplicator] = {}

_logger = getLogger("AHA (IPC)")

if cfg.cache_conv:
    _flag_mapping = FIFOCache(64)

MAX_WAITING_TASKS = 648
IS_PROCESS_MODE = cfg.execution_mode == "process"
IS_THREAD_MODE = cfg.execution_mode == "thread"


@define(slots=True)
class BotInstance:
    instance: Process | BaseBot
    platform: str
    if IS_THREAD_MODE:
        threading: Thread
    if IS_PROCESS_MODE:
        pipe: AsyncConnection | None = None
        calls: dict[str, Future] = field(factory=dict)
    server_ok: Event = field(factory=Event)
    wating_tasks_count: int = 0


# region instance manager
def _get_bot_id(bot_class, config):
    (hasher := xxh3_64(dumps(config))).update(bot_class)
    return hasher.intdigest()


async def _start_async_bot(bot: BaseBot, server_ok: Event):
    if not await bot.start():
        del_bot(bot.bot_id)
        server_ok.set()  # 让启动流程通过


async def spawn_bot_instance(bot_class: str, config: Mapping):
    bot_id = _get_bot_id(bot_class, config)
    if IS_PROCESS_MODE:
        event_parent, event_child = Pipe()

        bots[bot_id] = BotInstance(
            Process(
                target=api_process,
                args=(
                    cls := get_bot_class(bot_class),
                    bot_id,
                    event_child,
                    commented2basic(config),
                    cfg.base64_buffer,
                    cfg.lang,
                    log_config,
                ),
                daemon=True,
            ),
            cls.platform,
            pipe=AsyncConnection(event_parent),
        )
    elif IS_THREAD_MODE:
        bots[bot_id] = meta = BotInstance(obj := (cls := get_bot_class(bot_class))(bot_id, config), cls.platform)
        meta.threading = Thread(target=run_with_uvloop, args=(_start_async_bot(obj, meta.server_ok),), daemon=True)
    else:
        bots[bot_id] = BotInstance((cls := get_bot_class(bot_class))(bot_id, config), cls.platform)

    platform_bot_map[cls.platform].append(bot_id)
    if cls.platform not in deduplicators:
        deduplicators[cls.platform] = cls.deduplicator()

    return bot_id


async def start_bots():
    try:
        for i in cfg.bots:
            await spawn_bot_instance(*next(iter(i.items())))
    except TypeError as e:
        raise ValueError(_("api.service.config_error")) from e

    if IS_PROCESS_MODE:
        for v in bots.values():
            v.instance.start()
        for k, v in bots.items():
            create_task(monitor_processing_events(v.pipe, k))
    elif IS_THREAD_MODE:
        for v in bots.values():
            v.threading.start()
    else:
        for i in bots.values():
            create_task(_start_async_bot(i.instance, i.server_ok))

    await gather(*[v.server_ok.wait() for v in bots.values()])
    if not any(bots.values()):
        exit(1)


def del_bot(bot_id):
    bots[bot_id] = None
    for lst in platform_bot_map.values():
        try:
            lst.remove(bot_id)
            break
        except ValueError:
            continue


async def clean_bots():
    global bots, platform_bot_map
    with suppress(RuntimeError):
        await gather(*[call_api("close", bot=bot) for bot in bots], return_exceptions=True)

    if IS_PROCESS_MODE:
        for p in bots.values():
            if p:
                p.instance.close()
                p.instance.join()

    if IS_THREAD_MODE:
        for p in bots.values():
            if p:
                p.threading.join()

    bots = platform_bot_map = None


# endregion
# region event router
def get_trigger_by_enum(enum: APSTriggerType, kwargs):
    match enum:
        case APSTriggerType.TIME_TRIGGER:
            return TimeTrigger(**kwargs)
        case APSTriggerType.DATE_TRIGGER:
            return DateTrigger(**kwargs)
        case APSTriggerType.CORN_TRIGGER:
            return CronTrigger(**kwargs)
        case APSTriggerType.CALENDAR_INTERVAL_TRIGGER:
            return CalendarIntervalTrigger(**kwargs)
        case APSTriggerType.INTERVAL_TRIGGER:
            return IntervalTrigger(**kwargs)


def process_service_request(service: ServiceType, args, bot_id=None):
    match service:
        case ServiceType.ADD_SCHEDULE:
            args.api_kwargs.setdefault("bot", bot_id)
            create_task(
                scheduler.add_persist_schedule(
                    call_api,
                    get_trigger_by_enum(args.trigger, args.trigger_kwargs),
                    args=(args.api_method,),
                    kwargs=args.api_kwargs,
                    **args.schedule_kwargs,
                )
            )
        case ServiceType.RM_SCHEDULE_BY_META:
            create_task(scheduler.rm_persist_schedules_by_meta(args))


def event_route(bot_id, event_type, payload):
    match event_type:
        case EventCategory.META:
            if payload.event_type is MetaEventType.LIFECYCLE:
                if payload.sub_type is LifecycleSubType.CONNECT:
                    bots[payload.bot_id].server_ok.set()
                else:
                    bots[payload.bot_id].server_ok.clear()
            elif payload.status and not payload.status.online:
                bots[payload.bot_id].server_ok.clear()
            create_task(process_meta(payload))
        case EventCategory.CHAT:
            # get_msg API 调用缓存
            api_result_caches["get_msg"][hash(hashkey(bot_id, payload.message_id))] = payload

            if deduplicators[payload.platform].is_duplicate(payload):
                return
            create_task(process_message(payload))
        case EventCategory.NOTICE:
            # 会话列表维护
            if cfg.cache_conv and payload.event_type is NoticeEventType.FRIEND_ADD:
                from .router import users

                if (available_bots := (user_lst := users[payload.platform]).get(payload.user_id)) is None:
                    user_lst[payload.user_id] = available_bots = []
                available_bots.append(payload.bot_id)

            if deduplicators[payload.platform].is_duplicate(payload):
                return
            create_task(process_notice(payload))
        case EventCategory.REQUEST:
            # 会话列表维护
            if cfg.cache_conv and payload.event_type is RequestEventType.GROUP and payload.sub_type is RequestSubType.INVITE:
                _flag_mapping[payload.flag] = payload.group_id

            if deduplicators[payload.platform].is_duplicate(payload):
                return
            create_task(process_request(payload))
        case EventCategory.EXTERNAL:
            create_task(process_external(*payload))
        case EventCategory.RESPONSE:
            call_id, result = payload
            if future := bots[bot_id].calls.pop(call_id, None):
                if isinstance(result, BaseException):
                    future.set_exception(result)
                else:
                    future.set_result(result)
        case EventCategory.SERVICE_REQUEST:
            process_service_request(*payload, bot_id)


async def monitor_processing_events(pipe: AsyncConnection, bot_id):
    while True:
        try:
            event_route(bot_id, *await pipe.recv())
        except (EOFError, BrokenPipeError) as e:
            for c in (p := bots[bot_id]).calls.values():
                c.cancel()
            p.server_ok.set()  # 让启动流程通过
            del_bot(bot_id)
            break
        except Exception as e:
            _logger.error(_("router.listen_event.error") % e)
            await sleep(1)


# endregion
# call api and cache
NICKNAME_CACHE_CONFIG = cfg.register(
    "nickname", {"size": "1MiB", "cron": "0 0 * * *"}, _("router.cache.get_card_by_search"), "cache"
)

api_result_caches: dict[str, Cache | WeakValueDictionary] = {
    "get_card_by_search": CronMemLRUCache(parse_size(NICKNAME_CACHE_CONFIG["size"]), NICKNAME_CACHE_CONFIG["cron"]),
    "get_msg": WeakValueDictionary(),
}


async def call_api(method: str, *args, bot: int = None, **kwargs):
    # 缓存
    cache_key = None
    if (cacher := api_result_caches.get(method)) and (result := cacher.get(cache_key := hash(hashkey(bot, *args, **kwargs)))):
        return result

    # 服务存活检查
    try:
        if not (meta := bots[bot]):
            raise RuntimeError(_("router.api_closed"))
    except KeyError:
        _logger.warning(_("router.bot404"))
        raise

    call_id = token_hex(4)[:7]

    # 等待服务状态
    if IS_PROCESS_MODE:
        (calls := bots[bot].calls)[call_id] = future = get_running_loop().create_future()
    if not meta.server_ok.is_set():
        if meta.wating_tasks_count >= MAX_WAITING_TASKS:
            if IS_PROCESS_MODE:
                del calls[call_id]
            raise MemoryError(_("router.many_wating"))

        meta.wating_tasks_count += 1
        try:
            await meta.server_ok.wait()
        finally:
            meta.wating_tasks_count -= 1

    with suppress(CancelledError):
        if IS_PROCESS_MODE:
            try:
                await meta.pipe.send((call_id, method, args, kwargs))
            except (BrokenPipeError, EOFError) as e:
                del calls[call_id]
                raise RuntimeError(_("router.api_closed")) from e
            result = await future
        else:
            result = await getattr(meta.instance, method)(call_id, *args, **kwargs)

        if cfg.cache_conv and method == "set_group_add_request" and args[1] is True and (gid := _flag_mapping.get(args[0])):
            from .router import groups

            if (available_bots := (group_list := groups[meta.platform].get(gid))) is None:
                group_list[gid] = available_bots = []
            available_bots.append(bot)

        # 缓存
        if (cacher := api_result_caches.get(method)) is not None and isinstance(cacher, Cache):
            cacher[cache_key or hash(hashkey(bot, *args, **kwargs))] = (
                result.model_copy(deep=True) if isinstance(result, BaseModel) else deepcopy(result)
            )

        return result


# endregion
