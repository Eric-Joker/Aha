from contextlib import suppress

from anyio import Path
from sqlalchemy import JSON, String, TypeDecorator

with suppress(ImportError):
    from yarl import URL  # type: ignore

    class YarlURL(TypeDecorator):
        impl = String
        cache_ok = True

        def process_bind_param(self, value, _):
            return None if value is None else str(value)

        def process_result_value(self, value, _):
            return None if value is None else URL(value)


class Iterable(TypeDecorator):
    impl = JSON
    cache_ok = True

    def process_bind_param(self, value, _):
        return None if value is None else list(value)

    def process_result_value(self, value, _):
        return None if value is None else tuple(value)


class ComparablePath(Path):
    def __lt__(self, other):
        return str(self) < str(other)

    def __gt__(self, other):
        return str(self) > str(other)


class Path(TypeDecorator):
    impl = String(4096)
    cache_ok = True

    def process_bind_param(self, value, _):
        return None if value is None else str(value)

    def process_result_value(self, value, _):
        return None if value is None else ComparablePath(value)
