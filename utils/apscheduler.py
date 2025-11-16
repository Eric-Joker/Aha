from datetime import datetime, timedelta

from apscheduler._converters import as_aware_datetime
from apscheduler.triggers.date import DateTrigger
from attrs import define, field, validators


@define
class TimeTrigger(DateTrigger):
    """Triggers once after the specified number of seconds.

    :param seconds: the number of seconds to wait before triggering
    """

    seconds: int = field(converter=int)
    run_time: datetime = field(init=False, converter=as_aware_datetime, validator=validators.instance_of(datetime))

    @run_time.default
    def _default_run_time(self) -> datetime:
        return datetime.now() + timedelta(seconds=self.seconds)
