import inspect
import logging
from enum import StrEnum

from pydantic import BaseModel, Field

from fluidkit.codegen import build_schema_ts
from fluidkit.models import DecoratorType, FunctionMetadata, ParameterMetadata
from fluidkit.utilities import normalize_types

logging.basicConfig(level=logging.DEBUG)


class Status(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Address(BaseModel):
    street: str
    city: str
    zip_code: str | None = None


class User(BaseModel):
    id: int
    name: str
    status: Status = Status.ACTIVE
    address: Address | None = None
    tags: list[str] = Field(default_factory=list)


class Post(BaseModel):
    id: int
    title: str
    author: User


mock_functions = [
    FunctionMetadata(
        name="get_user",
        module="src.users.data",
        file_path="/project/src/users/data.py",
        decorator_type=DecoratorType.QUERY,
        return_annotation=normalize_types(User),
        parameters=[
            ParameterMetadata(
                name="user_id",
                annotation=normalize_types(str),
                default=inspect.Parameter.empty,
                required=True,
            )
        ],
    ),
    FunctionMetadata(
        name="get_posts",
        module="src.posts.data",
        file_path="/project/src/posts/data.py",
        decorator_type=DecoratorType.QUERY,
        return_annotation=normalize_types(list[Post]),
        parameters=[
            ParameterMetadata(
                name="limit",
                annotation=normalize_types(int | None),
                default=10,
                required=False,
            )
        ],
    ),
    FunctionMetadata(
        name="untyped_fn",
        module="src.misc",
        file_path="/project/src/misc.py",
        decorator_type=DecoratorType.COMMAND,
        return_annotation=normalize_types(inspect.Parameter.empty),
        parameters=[
            ParameterMetadata(
                name="data",
                annotation=normalize_types(inspect.Parameter.empty),
                default=inspect.Parameter.empty,
                required=True,
            )
        ],
    ),
]


def test_codegen():
    print(build_schema_ts(mock_functions))


if __name__ == "__main__":
    print(build_schema_ts(mock_functions))
