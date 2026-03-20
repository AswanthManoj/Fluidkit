from pydantic import BaseModel
from fluidkit import query, command, form


class User(BaseModel):
    name: str
    age: int


@query
async def get_number(n: int) -> int:
    """Should reject non-int values."""
    return n * 2


@query
async def get_greeting(name: str, loud: bool) -> str:
    """Should reject non-str name and non-bool loud."""
    if loud:
        return f"HELLO {name.upper()}!"
    return f"Hello {name}"


@command
async def create_user(user: User) -> dict:
    """Should validate full Pydantic model."""
    return {"created": user.name, "age": user.age}


@query
async def find_user(user_id: str) -> User | None:
    """Should reject non-str user_id."""
    if user_id == "1":
        return User(name="Alice", age=30)
    return None


@form
async def submit_feedback(rating: int, message: str):
    """Should validate rating as int, message as str."""
    return {"rating": rating, "message": message}
