from enum import Enum

from pydantic import BaseModel as PydanticBaseModel
from pydantic import ConfigDict


class BaseModel(PydanticBaseModel):
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True, validate_by_name=True, validate_default=False)

    def __repr__(self):  # 仅显示赋过值的
        return f"{self.__class__.__name__}({', '.join(f"{field_name}={getattr(self, field_name)!r}" for field_name in self.model_fields_set)})"

    @property
    def extra(self):
        return self.__pydantic_extra__
    
    
class FrozenBaseModel(BaseModel):
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True, validate_by_name=True, validate_default=False, frozen=True)


class PureNameEnum(Enum):
    def __repr__(self):
        return self.name
