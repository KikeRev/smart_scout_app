from pydantic import BaseModel
from typing import Annotated

class _Anon(BaseModel):
    id: str = "anon"


class User(BaseModel):
    id: int = 0               # minimum we need - an ID

def get_current_user() -> Annotated[User, "stub"]:
    """
    Placeholder version that simulates an authenticated user.
    Replace it when you add real auth.
    """
    return User(id=0)  