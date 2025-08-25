from pydantic import BaseModel
from typing import Annotated

class _Anon(BaseModel):
    id: str = "anon"


class User(BaseModel):
    id: int = 0               # lo mínimo que necesitamos - un ID

def get_current_user() -> Annotated[User, "stub"]:
    """
    Versión placeholder que simula un usuario autenticado.
    Sustitúyelo cuando añadas auth real.
    """
    return User(id=0)  