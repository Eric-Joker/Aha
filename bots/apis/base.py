
from secrets import token_hex
from typing import Any

from models.core import AddScheduleArgs, EventCategory, ServiceType


class BaseAPI:
    async def _call_api(self, echo, action, params=None, timeout=300) -> Any:
        """调用 `self.transport.send` 并获取返回值或报错"""
        raise NotImplementedError

    def gen_id(self):
        return token_hex(4)[:7]

    async def add_schedule(self, args: AddScheduleArgs):
        if self.is_processing_mode:
            await self.pipe_send(EventCategory.SERVICE_REQUEST, (ServiceType.ADD_SCHEDULE, args))
        else:
            from core.api_service import process_service_request

            process_service_request(ServiceType.ADD_SCHEDULE, args, self.bot_id)

    async def rm_schedule_by_meta(self, meta: dict):
        if self.is_processing_mode:
            await self.pipe_send(EventCategory.SERVICE_REQUEST, (ServiceType.RM_SCHEDULE_BY_META, meta))
        else:
            from core.api_service import process_service_request

            process_service_request(ServiceType.RM_SCHEDULE_BY_META, meta)
