from contextlib import suppress

from anyio import Path
from sqlalchemy import JSON, String, TypeDecorator

with suppress(ImportError):
    from yarl import URL

    class YarlURL(TypeDecorator):
        impl = String
        cache_ok = True  # 避免警告

        def process_bind_param(self, value: URL | None, _):
            return str(value)

        def process_result_value(self, value: str | None, _):
            return URL(value)


class Iterable(TypeDecorator):
    impl = JSON
    cache_ok = True  # 避免警告

    def process_bind_param(self, value, _):
        return list(value) if value else None

    def process_result_value(self, value, _):
        return tuple(value) if value else None


class ComparablePath(Path):
    def __lt__(self, other):
        return str(self) < str(other)

    def __gt__(self, other):
        return str(self) > str(other)


class Path(TypeDecorator):
    impl = String(4096)
    cache_ok = True  # 避免警告

    def process_bind_param(self, value: Path | None, _):
        return str(value)

    def process_result_value(self, value: str | None, _):
        return ComparablePath(value)
