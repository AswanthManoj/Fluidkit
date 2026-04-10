import inspect
from enum import StrEnum
from typing import Any, Generic, TypeVar
from pydantic import BaseModel, ConfigDict, Field


class BaseType(StrEnum):
    ANY = "any"
    NULL = "null"
    VOID = "void"
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    FILE = "__FluidKitFile__"


class ContainerType(StrEnum):
    ARRAY = "array"
    UNION = "union"
    TUPLE = "tuple"
    RECORD = "record"
    LITERAL = "literal"
    OPTIONAL = "optional"


class DecoratorType(StrEnum):
    FORM = "form"
    QUERY = "query"
    COMMAND = "command"
    PRERENDER = "prerender"
    QUERY_BATCH = "query_batch"


class HookType(StrEnum):
    INIT = "init"
    CLEANUP = "cleanup"
    LIFESPAN = "lifespan"
    HANDLE = "handle"
    HANDLE_ERROR = "handle_error"
    HANDLE_VALIDATION_ERROR = "handle_validation_error"


class MutationType(StrEnum):
    SET = "set"
    REFRESH = "refresh"


# ── FluidKit Metadata Models ────────────────────────────────────────────────

class MutationEntry(BaseModel):
    """Base model for a mutation entry"""

    key: str
    args: dict[str, Any]
    data: Any
    mutation_type: MutationType


class FluidKitMetadata(BaseModel):
    """Metadata for single-flight mutations and cookie instructions"""

    cookies: list[dict] = Field(default_factory=list)
    mutations: list[MutationEntry] = Field(default_factory=list)


class FieldAnnotation(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    base_type: BaseType | None = None
    container: ContainerType | None = None
    args: list["FieldAnnotation"] = Field(default_factory=list)
    literal_values: list = Field(default_factory=list)
    custom_type: str | None = None
    class_reference: Any | None = None


class ParameterMetadata(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    annotation: FieldAnnotation
    default: Any = inspect.Parameter.empty
    required: bool


class FunctionMetadata(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    docstring: str | None = None
    return_annotation: FieldAnnotation
    parameters: list[ParameterMetadata]
    file_path: str | None = None
    module: str
    decorator_type: DecoratorType
    prerender_inputs: Any | None = None
    prerender_dynamic: bool = False



class RedirectData(BaseModel):
    """Redirect information"""

    status: int = Field(ge=300, le=308)
    location: str


# ── Hooks Models ────────────────────────────────────────────────

class HookRequestContext(BaseModel):
    """Context sent to Python with each remote function call."""
    url: str
    method: str
    cookies: list[dict[str, str]]
    headers: dict[str, str]
    is_remote: bool


# ── Response Models ─────────────────────────────────────────────────────────

T = TypeVar("T")


class QueryResponse(BaseModel, Generic[T]):
    """Response for @query and @prerender"""

    model_config = ConfigDict(populate_by_name=True)

    result: T
    fk_locals: dict[str, Any] = Field(default_factory=dict, alias="__fk_locals")


class BatchQueryResponse(BaseModel):
    """Response for @query.batch"""

    model_config = ConfigDict(populate_by_name=True)

    results: list[Any]
    fk_locals: dict[str, Any] = Field(default_factory=dict, alias="__fk_locals")


class CommandResponse(BaseModel, Generic[T]):
    """Response for @command and @form (success)"""

    model_config = ConfigDict(populate_by_name=True)

    result: T
    fk_locals: dict[str, Any] = Field(default_factory=dict, alias="__fk_locals")
    fk_cookies: list[dict[str, Any]] = Field(default_factory=list, alias="__fk_cookies")
    fluidkit_metadata: FluidKitMetadata = Field(default_factory=FluidKitMetadata, alias="__fluidkit")


class RedirectResponse(BaseModel):
    """Response for @command/@form with redirect"""

    model_config = ConfigDict(populate_by_name=True)

    redirect: RedirectData
    fk_locals: dict[str, Any] = Field(default_factory=dict, alias="__fk_locals")
    fk_cookies: list[dict[str, Any]] = Field(default_factory=list, alias="__fk_cookies")
    fluidkit_metadata: FluidKitMetadata = Field(default_factory=FluidKitMetadata, alias="__fluidkit")


# ── Error Models ────────────────────────────────────────────────────────────

class FluidKitErrorDetails(BaseModel):
    """Error details for development mode"""

    type: str
    traceback: str


class UnhandledErrorResponse(BaseModel):
    """Response for unhandled exceptions in dev mode"""

    message: str
    error_details: FluidKitErrorDetails | None = Field(default=None, alias="__fluidkit_error")


# ── Request Models (for endpoints) ──────────────────────────────────────────

class FileUploadInfo(BaseModel):
    """Metadata for file uploads (not the file itself)"""

    filename: str
    content_type: str
    size: int


class FluidKitEnvelope(BaseModel):
    """Request envelope wrapping hook context and function payload."""
    
    model_config = ConfigDict(populate_by_name=True)
    
    fk_context: HookRequestContext | None = Field(None, alias="__fk_context")
    fk_payload: dict[str, Any] = Field(default_factory=dict, alias="__fk_payload")


# ── Helper Functions ────────────────────────────────────────────────────────

def create_query_response(result: Any, locals: dict = None) -> QueryResponse:
    """Create a query response"""
    return QueryResponse(result=result, fk_locals=locals or {})


def create_batch_query_response(results: list[Any], locals: dict = None) -> BatchQueryResponse:
    """Create a batch query response"""
    return BatchQueryResponse(results=results, fk_locals=locals or {})


def create_command_response(
    result: Any,
    mutations: list[MutationEntry] = None,
    cookies: list[dict] = None,
    locals: dict = None
) -> CommandResponse:
    """Create a command response with optional mutations and cookie instructions"""
    metadata = FluidKitMetadata(mutations=mutations or [], cookies=cookies or [])
    return CommandResponse(result=result, __fluidkit=metadata, fk_locals=locals or {}, fk_cookies=cookies or [])


def create_redirect_response(
    status: int,
    location: str,
    cookies: list[dict] = None,
    locals: dict = None
) -> RedirectResponse:
    redirect_data = RedirectData(status=status, location=location)
    metadata = FluidKitMetadata(cookies=cookies or [])
    return RedirectResponse(redirect=redirect_data, __fluidkit=metadata, fk_locals=locals or {}, fk_cookies=cookies or [])


def create_error_response(
    e: Exception | None = None, message: str | None = None, *, dev: bool = False
) -> UnhandledErrorResponse:
    """Create an error response, including details in development mode"""
    if e is not None and dev:
        import traceback

        return UnhandledErrorResponse(
            message=str(e),
            __fluidkit_error=FluidKitErrorDetails(type=type(e).__name__, traceback=traceback.format_exc()),
        )
    return UnhandledErrorResponse(message=message or "An unexpected error occurred")
