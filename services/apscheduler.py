import apscheduler

if hasattr(apscheduler, "__version__"):
    raise ImportError("apscheduler 需要 4.0 或以上版本。")

import logging
from collections.abc import Callable, Iterable, Mapping
from contextlib import AsyncExitStack
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

from apscheduler import AsyncScheduler, JobReleased, JobResult, CoalescePolicy, ConflictPolicy, JobOutcome
from apscheduler._exceptions import DeserializationError
from apscheduler._schedulers.async_ import TaskType
from apscheduler._structures import MetadataType, Job, Task, Schedule
from apscheduler._marshalling import callable_from_ref
from apscheduler._utils import UnsetValue, unset
from apscheduler.abc import Serializer, Trigger
from apscheduler.datastores.sqlalchemy import SQLAlchemyDataStore

from core.database import db_engine
from models.metas import SingletonMeta

# from wrapt import when_imported


__all__ = "sched"


# region monkey patch
"""# region 元数据自动将 bytes 转为 int
def valid_metadata(_, attribute, value):
    def check_value(path, val):
        if val is None:
            return val

        if isinstance(val, list):
            for index, item in enumerate(val):
                if (new_item := check_value(f"{path}[{index}]", item)) is not item:
                    val[index] = new_item
            return val
        elif isinstance(val, dict):
            for k, v in val.items():
                if not isinstance(k, str):
                    raise ValueError(f"{path} has a non-string key ({k!r})")

                if (new_v := check_value(f"{path}[{k!r}]", v)) is not v:
                    val[k] = new_v
            return val
        elif isinstance(val, bytes) and len(val) <= 8:
            return int.from_bytes(val, "big")
        elif isinstance(val, (str, int, float, bool)):
            return val
        raise ValueError(f"{path} has a value that is not JSON compatible: ({val!r})")

    if not isinstance(value, dict):
        raise ValueError(f"{attribute.name} must be a dict, got: {value!r}")

    for key, val in value.items():
        if (new_val := check_value(key, val)) is not val:
            value[key] = new_val


when_imported("apscheduler._validators")(lambda m: setattr(m, "valid_metadata", valid_metadata))
# endregion"""


# region 当目标任务模块不存在时，让 data_store 的 acquire_jobs 进入丢弃 Job 逻辑。
_original_unmarshal = Job.unmarshal


@classmethod
def unmarshal(cls, serializer: Serializer, marshalled: dict[str, Any]):
    try:
        callable_from_ref(marshalled["task_id"])
    except LookupError:
        raise DeserializationError

    return _original_unmarshal(serializer, marshalled)


Job.unmarshal = unmarshal
# endregion
# endregion


class Scheduler(metaclass=SingletonMeta):
    """所有方法存在两个版本，一个用于持久任务或其调度器，一个用于程序生命周期内的瞬态任务或其调度器"""

    __slots__ = ("persistent_scheduler", "transient_scheduler", "_exit_stack")

    data_store = SQLAlchemyDataStore(db_engine)

    def __init__(self):
        self.persistent_scheduler = AsyncScheduler(self.data_store, cleanup_interval=None)
        self.transient_scheduler = AsyncScheduler(cleanup_interval=None)
        self._exit_stack = AsyncExitStack()

    async def start(self):
        await self._exit_stack.enter_async_context(self.persistent_scheduler)
        await self._exit_stack.enter_async_context(self.transient_scheduler)

        await self.persistent_scheduler.start_in_background()
        await self.transient_scheduler.start_in_background()

        self.persistent_scheduler.subscribe(self._persist_sched_cleanup, {JobReleased}, one_shot=False)
        self.transient_scheduler.subscribe(self._cleanup, {JobReleased}, one_shot=False)

    async def stop(self):
        await self._exit_stack.aclose()

    # region persistent scheduler
    async def _persist_sched_cleanup(self, *_):
        return await self.persistent_scheduler.cleanup()

    async def persist_sched_configure_task(
        self,
        func: Callable[..., Any] | UnsetValue,
        *,
        job_executor: str | UnsetValue = unset,
        misfire_grace_time: float | timedelta | None | UnsetValue = unset,
        max_running_jobs: int | None | UnsetValue = unset,
        metadata: MetadataType | UnsetValue = unset,
    ) -> Task:
        """
        Add or update a :ref:`task <task>` definition.

        Any options not explicitly passed to this method will use their default values
        (from ``task_defaults``) when a new task is created:

        * ``job_executor``: the value of ``default_job_executor`` scheduler attribute
        * ``misfire_grace_time``: ``None``
        * ``max_running_jobs``: 1

        When updating a task, any options not explicitly passed will remain the same.

        :param func: a callable that will be associated with the task
        :param job_executor: name of the job executor to run the task with
        :param misfire_grace_time: maximum number of seconds the scheduled job's actual
            run time is allowed to be late, compared to the scheduled run time
        :param max_running_jobs: maximum number of instances of the task that are
            allowed to run concurrently
        :param metadata: key-value pairs for storing JSON compatible custom information
        :raises TypeError: if ``func_or_task_id`` is neither a task, task ID or a
            callable
        :return: the created or updated task definition

        """
        return await self.persistent_scheduler.configure_task(
            func,
            job_executor=job_executor,
            misfire_grace_time=misfire_grace_time,
            max_running_jobs=max_running_jobs,
            metadata=metadata,
        )

    async def persist_sched_get_tasks(self, *, id: str = None, func: Callable[..., Any] = None, metadata: MetadataType = None):
        """
        Retrieve currently defined tasks.

        :return: a sequence of tasks, sorted by ID

        """
        tasks = await self.persistent_scheduler.get_tasks()
        hi, hf, hm = bool(id), bool(func), bool(metadata)

        if not hi and not hf and not hm:
            return None

        return [
            t for t in tasks if (not hi or t.id == id) and (not hf or t.func is func) and (not hm or t.metadata == metadata)
        ]

    async def add_persist_schedule(
        self,
        func_or_task_id: TaskType,
        trigger: Trigger,
        *,
        id: str | None = None,
        args: Iterable[Any] | None = None,
        kwargs: Mapping[str, Any] | None = None,
        paused: bool = False,
        coalesce: CoalescePolicy = CoalescePolicy.latest,
        job_executor: str | UnsetValue = unset,
        misfire_grace_time: float | timedelta | None | UnsetValue = unset,
        metadata: MetadataType | UnsetValue = unset,
        max_jitter: float | timedelta | None = None,
        job_result_expiration_time: float | timedelta = 0,
        conflict_policy: ConflictPolicy = ConflictPolicy.do_nothing,
    ) -> str:
        """
        Schedule a task to be run one or more times in the future.

        :param func_or_task_id: either a callable or an ID of an existing task
            definition
        :param trigger: determines the times when the task should be run
        :param id: an explicit identifier for the schedule (if omitted, a random, UUID
            based ID will be assigned)
        :param args: positional arguments to be passed to the task function
        :param kwargs: keyword arguments to be passed to the task function
        :param paused: whether the schedule is paused
        :param job_executor: name of the job executor to run the scheduled jobs with
            (overrides the executor specified in the task settings)
        :param coalesce: determines what to do when processing the schedule if multiple
            fire times have become due for this schedule since the last processing
        :param misfire_grace_time: maximum number of seconds the scheduled job's actual
            run time is allowed to be late, compared to the scheduled run time
        :param metadata: key-value pairs for storing JSON compatible custom information
        :param max_jitter: maximum time (in seconds, or as a timedelta) to randomly add
            to the scheduled time for each job created from this schedule
        :param job_result_expiration_time: minimum time (in seconds, or as a timedelta)
            to keep the job results in storage from the jobs created by this schedule
        :param conflict_policy: determines what to do if a schedule with the same ID
            already exists in the data store
        :return: the ID of the newly added schedule

        """
        return await self.persistent_scheduler.add_schedule(
            func_or_task_id,
            trigger,
            id=id,
            args=args,
            kwargs=kwargs,
            paused=paused,
            coalesce=coalesce,
            job_executor=job_executor,
            misfire_grace_time=misfire_grace_time,
            metadata=metadata,
            max_jitter=max_jitter,
            job_result_expiration_time=job_result_expiration_time,
            conflict_policy=conflict_policy,
        )

    async def get_persist_schedule(self, id: str) -> Schedule:
        """
        Retrieve a schedule from the data store.

        :param id: the unique identifier of the schedule
        :raises ScheduleLookupError: if the schedule could not be found

        """
        return await self.persistent_scheduler.get_schedule(id)

    async def get_persist_schedules(self, *, id: str = None, task_id: str = None, metadata: MetadataType = None):
        """
        Retrieve schedules from the data store.

        :return: a list of schedules, in an unspecified order

        """
        ss = await self.persistent_scheduler.get_schedules()
        hi, ht, hm = bool(id), bool(task_id), bool(metadata)

        if not hi and not ht and not hm:
            return None

        return [
            s for s in ss if (not hi or s.id == id) and (not ht or s.task_id == task_id) and (not hm or s.metadata == metadata)
        ]

    async def remove_persist_schedule(self, id: str) -> None:
        """
        Remove the given schedule from the data store.

        :param id: the unique identifier of the schedule

        """
        return await self.persistent_scheduler.remove_schedule(id)

    async def rm_persist_schedules_by_meta(self, metadata: MetadataType):
        # try:
        for schedule in (schedules := await self.get_persist_schedules(metadata=metadata)):
            await self.persistent_scheduler.remove_schedule(schedule)
        # except:
        #    await post_msg_to_supers(f"删除计划任务时出现异常，为防止意外情况，终止机器人运行。\n{format_exc()}")
        #    core.status.main_task.cancel()
        return len(schedules)

    async def pause_persist_schedule(self, id: str) -> None:
        """Pause the specified schedule."""
        return await self.persistent_scheduler.pause_schedule(id)

    async def unpause_persist_schedule(self, id: str, *, resume_from: datetime | Literal["now"] | None = None) -> None:
        """
        Unpause the specified schedule.


        :param resume_from: the time to resume the schedules from, or ``'now'`` as a
            shorthand for ``datetime.now(tz=UTC)`` or ``None`` to resume from where the
            schedule left off which may cause it to misfire

        """
        return await self.persistent_scheduler.unpause_schedule(id, resume_from=resume_from)

    async def add_persist_job(
        self,
        func_or_task_id: TaskType,
        *,
        args: Iterable[Any] | None = None,
        kwargs: Mapping[str, Any] | None = None,
        job_executor: str | UnsetValue = unset,
        metadata: MetadataType | UnsetValue = unset,
        result_expiration_time: timedelta | float = 0,
    ) -> UUID:
        """
        Add a job to the data store.

        :param func_or_task_id:
            Either the ID of a pre-existing task, or a function/method. If a function is
            given, a task will be created with the fully qualified name of the function
            as the task ID (unless that task already exists of course).
        :param args: positional arguments to call the target callable with
        :param kwargs: keyword arguments to call the target callable with
        :param job_executor: name of the job executor to run the task with
            (overrides the executor in the task definition, if any)
        :param metadata: key-value pairs for storing JSON compatible custom information
        :param result_expiration_time: the minimum time (as seconds, or timedelta) to
            keep the result of the job available for fetching (the result won't be
            saved at all if that time is 0)
        :return: the ID of the newly created job

        """
        return await self.persistent_scheduler.add_job(
            func_or_task_id,
            args=args,
            kwargs=kwargs,
            job_executor=job_executor,
            metadata=metadata,
            result_expiration_time=result_expiration_time,
        )

    async def get_persist_jobs(
        self, *, id: UUID = None, task_id: str = None, schedule_id: str = None, metadata: MetadataType = None
    ):
        """Retrieve jobs from the data store."""
        jobs = await self.persistent_scheduler.get_jobs()
        has_id, has_task, has_schedule, has_metadata = bool(id), bool(task_id), bool(schedule_id), bool(metadata)

        if not has_id and not has_task and not has_schedule and not has_metadata:
            return None

        return [
            j
            for j in jobs
            if (not has_id or j.id == id)
            and (not has_task or j.task_id == task_id)
            and (not has_schedule or j.schedule_id == schedule_id)
            and (not has_metadata or j.metadata == metadata)
        ]

    async def get_persist_job_result(self, job_id: UUID, *, wait: bool = True) -> JobResult | None:
        """
        Retrieve the result of a job.

        :param job_id: the ID of the job
        :param wait: if ``True``, wait until the job has ended (one way or another),
            ``False`` to raise an exception if the result is not yet available
        :returns: the job result, or ``None`` if the job finished but didn't record a
            result (``result_expiration_time`` was 0 or a similarly short time interval
            that did not allow for the result to be fetched before it was deleted)
        :raises JobLookupError: if neither the job or its result exist in the data
            store, or the job exists but the result is not ready yet and ``wait=False``
            is set

        """
        return await self.persistent_scheduler.get_job_result(job_id, wait=wait)

    async def run_persist_job(
        self,
        func_or_task_id: str | Callable[..., Any],
        *,
        args: Iterable[Any] | None = None,
        kwargs: Mapping[str, Any] | None = None,
        job_executor: str | UnsetValue = unset,
        metadata: MetadataType | UnsetValue = unset,
    ) -> Any:
        """
        Convenience method to add a job and then return its result.

        If the job raised an exception, that exception will be reraised here.

        :param func_or_task_id: either a callable or an ID of an existing task
            definition
        :param args: positional arguments to be passed to the task function
        :param kwargs: keyword arguments to be passed to the task function
        :param job_executor: name of the job executor to run the task with
            (overrides the executor in the task definition, if any)
        :param metadata: key-value pairs for storing JSON compatible custom information
        :returns: the return value of the task function

        """
        return await self.persistent_scheduler.run_job(
            func_or_task_id, args=args, kwargs=kwargs, job_executor=job_executor, metadata=metadata
        )

    # endregion

    # region transient_scheduler
    async def _cleanup(self, *_):
        return await self.transient_scheduler.cleanup()

    async def reset_temp_sched(self):
        now = datetime.now(timezone.utc)
        if schedules := await self.transient_scheduler.get_schedules():
            await self.transient_scheduler.data_store.remove_schedules([s.id for s in schedules])
        self.transient_scheduler.data_store._schedules_by_task_id.clear()
        for task in await self.transient_scheduler.get_tasks():
            await self.transient_scheduler.data_store.remove_task(task.id)
        for job in tuple(self.transient_scheduler.data_store._jobs_by_id.values()):
            await self.transient_scheduler.data_store.release_job(
                job.acquired_by or "", job, JobResult.from_job(job=job, outcome=JobOutcome.abandoned, finished_at=now)
            )
        self.transient_scheduler.data_store._job_results.clear()
        self.transient_scheduler._running_jobs.clear()
        self.transient_scheduler._task_callables.clear()

    async def configure_task(
        self,
        func_or_task_id: TaskType,
        *,
        func: Callable[..., Any] | UnsetValue = unset,
        job_executor: str | UnsetValue = unset,
        misfire_grace_time: float | timedelta | None | UnsetValue = unset,
        max_running_jobs: int | None | UnsetValue = unset,
        metadata: MetadataType | UnsetValue = unset,
    ) -> Task:
        """
        Add or update a :ref:`task <task>` definition.

        Any options not explicitly passed to this method will use their default values
        (from ``task_defaults``) when a new task is created:

        * ``job_executor``: the value of ``default_job_executor`` scheduler attribute
        * ``misfire_grace_time``: ``None``
        * ``max_running_jobs``: 1

        When updating a task, any options not explicitly passed will remain the same.

        :param func: a callable that will be associated with the task
        :param job_executor: name of the job executor to run the task with
        :param misfire_grace_time: maximum number of seconds the scheduled job's actual
            run time is allowed to be late, compared to the scheduled run time
        :param max_running_jobs: maximum number of instances of the task that are
            allowed to run concurrently
        :param metadata: key-value pairs for storing JSON compatible custom information
        :raises TypeError: if ``func_or_task_id`` is neither a task, task ID or a
            callable
        :return: the created or updated task definition

        """
        return await self.transient_scheduler.configure_task(
            func_or_task_id,
            func=func,
            job_executor=job_executor,
            misfire_grace_time=misfire_grace_time,
            max_running_jobs=max_running_jobs,
            metadata=metadata,
        )

    async def get_tasks(self, *, id: str = None, func: Callable[..., Any] = None, metadata: MetadataType = None):
        """
        Retrieve currently defined tasks.

        :return: a sequence of tasks, sorted by ID

        """
        tasks = await self.transient_scheduler.get_tasks()
        hi, hf, hm = bool(id), bool(func), bool(metadata)

        if not hi and not hf and not hm:
            return None

        return [
            t for t in tasks if (not hi or t.id == id) and (not hf or t.func is func) and (not hm or t.metadata == metadata)
        ]

    async def add_schedule(
        self,
        func_or_task_id: TaskType,
        trigger: Trigger,
        *,
        id: str | None = None,
        args: Iterable[Any] | None = None,
        kwargs: Mapping[str, Any] | None = None,
        paused: bool = False,
        coalesce: CoalescePolicy = CoalescePolicy.latest,
        job_executor: str | UnsetValue = unset,
        misfire_grace_time: float | timedelta | None | UnsetValue = unset,
        metadata: MetadataType | UnsetValue = unset,
        max_jitter: float | timedelta | None = None,
        job_result_expiration_time: float | timedelta = 0,
        conflict_policy: ConflictPolicy = ConflictPolicy.do_nothing,
    ) -> str:
        """
        Schedule a task to be run one or more times in the future.

        :param func_or_task_id: either a callable or an ID of an existing task
            definition
        :param trigger: determines the times when the task should be run
        :param id: an explicit identifier for the schedule (if omitted, a random, UUID
            based ID will be assigned)
        :param args: positional arguments to be passed to the task function
        :param kwargs: keyword arguments to be passed to the task function
        :param paused: whether the schedule is paused
        :param job_executor: name of the job executor to run the scheduled jobs with
            (overrides the executor specified in the task settings)
        :param coalesce: determines what to do when processing the schedule if multiple
            fire times have become due for this schedule since the last processing
        :param misfire_grace_time: maximum number of seconds the scheduled job's actual
            run time is allowed to be late, compared to the scheduled run time
        :param metadata: key-value pairs for storing JSON compatible custom information
        :param max_jitter: maximum time (in seconds, or as a timedelta) to randomly add
            to the scheduled time for each job created from this schedule
        :param job_result_expiration_time: minimum time (in seconds, or as a timedelta)
            to keep the job results in storage from the jobs created by this schedule
        :param conflict_policy: determines what to do if a schedule with the same ID
            already exists in the data store
        :return: the ID of the newly added schedule

        """
        return await self.transient_scheduler.add_schedule(
            func_or_task_id,
            trigger,
            id=id,
            args=args,
            kwargs=kwargs,
            paused=paused,
            coalesce=coalesce,
            job_executor=job_executor,
            misfire_grace_time=misfire_grace_time,
            metadata=metadata,
            max_jitter=max_jitter,
            job_result_expiration_time=job_result_expiration_time,
            conflict_policy=conflict_policy,
        )

    async def get_schedule(self, id: str) -> Schedule:
        """
        Retrieve a schedule from the data store.

        :param id: the unique identifier of the schedule
        :raises ScheduleLookupError: if the schedule could not be found

        """
        return await self.transient_scheduler.get_schedule(id)

    async def get_schedules(self, *, id: str = None, task_id: str = None, metadata: MetadataType = None):
        """
        Retrieve schedules from the data store.

        :return: a list of schedules, in an unspecified order

        """
        ss = await self.transient_scheduler.get_schedules()
        hi, ht, hm = bool(id), bool(task_id), bool(metadata)

        if not hi and not ht and not hm:
            return None

        return [
            s for s in ss if (not hi or s.id == id) and (not ht or s.task_id == task_id) and (not hm or s.metadata == metadata)
        ]

    async def remove_schedule(self, id: str) -> None:
        """
        Remove the given schedule from the data store.

        :param id: the unique identifier of the schedule

        """
        return await self.transient_scheduler.remove_schedule(id)

    async def rm_schedules_by_meta(self, metadata: MetadataType):
        # try:
        for schedule in (schedules := await self.get_schedules(metadata=metadata)):
            await self.transient_scheduler.remove_schedule(schedule)
        # except:
        #    await post_msg_to_supers(f"删除计划任务时出现异常，为防止意外情况，终止机器人运行。\n{format_exc()}")
        #    core.status.main_task.cancel()
        return len(schedules)

    async def pause_schedule(self, id: str) -> None:
        """Pause the specified schedule."""
        return await self.transient_scheduler.pause_schedule(id)

    async def unpause_schedule(self, id: str, *, resume_from: datetime | Literal["now"] | None = None) -> None:
        """
        Unpause the specified schedule.


        :param resume_from: the time to resume the schedules from, or ``'now'`` as a
            shorthand for ``datetime.now(tz=UTC)`` or ``None`` to resume from where the
            schedule left off which may cause it to misfire

        """
        return await self.transient_scheduler.unpause_schedule(id, resume_from=resume_from)

    async def add_job(
        self,
        func_or_task_id: TaskType,
        *,
        args: Iterable[Any] | None = None,
        kwargs: Mapping[str, Any] | None = None,
        job_executor: str | UnsetValue = unset,
        metadata: MetadataType | UnsetValue = unset,
        result_expiration_time: timedelta | float = 0,
    ) -> UUID:
        """
        Add a job to the data store.

        :param func_or_task_id:
            Either the ID of a pre-existing task, or a function/method. If a function is
            given, a task will be created with the fully qualified name of the function
            as the task ID (unless that task already exists of course).
        :param args: positional arguments to call the target callable with
        :param kwargs: keyword arguments to call the target callable with
        :param job_executor: name of the job executor to run the task with
            (overrides the executor in the task definition, if any)
        :param metadata: key-value pairs for storing JSON compatible custom information
        :param result_expiration_time: the minimum time (as seconds, or timedelta) to
            keep the result of the job available for fetching (the result won't be
            saved at all if that time is 0)
        :return: the ID of the newly created job

        """
        return await self.transient_scheduler.add_job(
            func_or_task_id,
            args=args,
            kwargs=kwargs,
            job_executor=job_executor,
            metadata=metadata,
            result_expiration_time=result_expiration_time,
        )

    async def get_jobs(self, *, id: UUID = None, task_id: str = None, schedule_id: str = None, metadata: MetadataType = None):
        """Retrieve jobs from the data store."""
        jobs = await self.transient_scheduler.get_jobs()
        has_id, has_task, has_schedule, has_metadata = bool(id), bool(task_id), bool(schedule_id), bool(metadata)

        if not has_id and not has_task and not has_schedule and not has_metadata:
            return None

        return [
            j
            for j in jobs
            if (not has_id or j.id == id)
            and (not has_task or j.task_id == task_id)
            and (not has_schedule or j.schedule_id == schedule_id)
            and (not has_metadata or j.metadata == metadata)
        ]

    async def get_job_result(self, job_id: UUID, *, wait: bool = True) -> JobResult | None:
        """
        Retrieve the result of a job.

        :param job_id: the ID of the job
        :param wait: if ``True``, wait until the job has ended (one way or another),
            ``False`` to raise an exception if the result is not yet available
        :returns: the job result, or ``None`` if the job finished but didn't record a
            result (``result_expiration_time`` was 0 or a similarly short time interval
            that did not allow for the result to be fetched before it was deleted)
        :raises JobLookupError: if neither the job or its result exist in the data
            store, or the job exists but the result is not ready yet and ``wait=False``
            is set

        """
        return await self.transient_scheduler.get_job_result(job_id, wait=wait)

    async def run_job(
        self,
        func_or_task_id: str | Callable[..., Any],
        *,
        args: Iterable[Any] | None = None,
        kwargs: Mapping[str, Any] | None = None,
        job_executor: str | UnsetValue = unset,
        metadata: MetadataType | UnsetValue = unset,
    ) -> Any:
        """
        Convenience method to add a job and then return its result.

        If the job raised an exception, that exception will be reraised here.

        :param func_or_task_id: either a callable or an ID of an existing task
            definition
        :param args: positional arguments to be passed to the task function
        :param kwargs: keyword arguments to be passed to the task function
        :param job_executor: name of the job executor to run the task with
            (overrides the executor in the task definition, if any)
        :param metadata: key-value pairs for storing JSON compatible custom information
        :returns: the return value of the task function

        """
        return await self.transient_scheduler.run_job(
            func_or_task_id, args=args, kwargs=kwargs, job_executor=job_executor, metadata=metadata
        )

    # endregion


sched = Scheduler()

logging.getLogger().addFilter(
    lambda record: record.levelno != logging.ERROR
    or record.getMessage()
    != "The scheduler has not been initialized yet. Use the scheduler as an async context manager (async with ...) in order to call methods other than run_until_stopped()."
)
logging.getLogger("apscheduler._schedulers.async_").addFilter(
    lambda record: record.levelno != logging.INFO
    or (msg := record.getMessage()) != "Scheduler started"
    and msg != "Scheduler stopped"
)
