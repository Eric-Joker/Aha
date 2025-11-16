from ..base import FrozenBaseModel


class APIVersion(FrozenBaseModel):
    app_name: str
    protocol_version: str
    app_version: str
