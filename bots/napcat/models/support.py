from collections.abc import Iterable
from typing import TYPE_CHECKING, overload

from models.base import FrozenBaseModel


class AICharacter(FrozenBaseModel):
    character_id: str
    character_name: str
    preview_url: str


class AICharacterList(list[AICharacter]):
    if TYPE_CHECKING:

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
