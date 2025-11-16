from logging import getLogger
from secrets import token_hex
from typing import TYPE_CHECKING

from core.log import AhaLogger
from models.core import AddScheduleArgs, EventCategory, ServiceType

if TYPE_CHECKING:
    from .. import BaseBot


class BaseAPI:
    def __init__(self):
        self.logger: AhaLogger = getLogger(self.__class__.__name__)

    @staticmethod
    def gen_id():
        return token_hex(4)[:7]

    async def _service_request(self: BaseBot, service_type, args):
        if self.is_process_mode:
            await self.event_post(EventCategory.SERVICE_REQUEST, (service_type, args))
        else:
            from core.api_service import process_service_request

            process_service_request(service_type, args, self.bot_id)

    async def add_schedule(self, args: AddScheduleArgs):
        await self._service_request(ServiceType.ADD_SCHEDULE, args)

    async def rm_schedule_by_meta(self, meta: dict):
        await self._service_request(ServiceType.RM_SCHEDULE_BY_META, meta)
