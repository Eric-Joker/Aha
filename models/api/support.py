from collections.abc import Iterable
from typing import overload

from ..base import BaseModelConfig


class AICharacter(BaseModelConfig):
    """qq"""
    character_id: str
    character_name: str
    preview_url: str

    def get_details(self) -> dict:
        return {"character_id": self.character_id, "character_name": self.character_name, "preview_url": self.preview_url}


class AICharacterList(list[AICharacter]):
    @overload
    def __init__(self) -> None: ...

    @overload
    def __init__(self, *elements: dict | AICharacter) -> None: ...

    @overload
    def __init__(self, iterable: Iterable[dict | AICharacter], /) -> None: ...

    def __init__(self, *args):
        if not args:
            super().__init__()
        elif len(args) == 1:
            if isinstance(arg := args[0], dict):
                super().__init__((AICharacter.model_validate(arg),))
            elif isinstance(arg, AICharacter):
                super().__init__(args)
            else:
                super().__init__(AICharacter.model_validate(a) if isinstance(a, dict) else a for a in arg)
        else:
            super().__init__(AICharacter.model_validate(arg) if isinstance(arg, dict) else arg for arg in args)

    def get_search_id_by_name(self, name: str) -> str | None:
        return next((character.character_id for character in self if character.character_name == name), None)


class APIVersion(BaseModelConfig):
    app_name: str
    protocol_version: str
    app_version: str
