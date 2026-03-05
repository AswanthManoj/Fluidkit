import inspect
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Dict, Optional, List, Generic, TypeVar


class BaseType(str, Enum):
    ANY = "any"
    NULL = "null"
    VOID = "void"
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    FILE = "__FluidKitFile__"


class ContainerType(str, Enum):
    ARRAY = "array"
    UNION = "union"
    TUPLE = "tuple"
    RECORD = "record"
    LITERAL = "literal"
    OPTIONAL = "optional"


class DecoratorType(str, Enum):
    FORM = "form"
    QUERY = "query"
    COMMAND = "command"
    PRERENDER = "prerender"
    QUERY_BATCH = "query_batch"

class MutationType(str, Enum):
    SET = "set"
    REFRESH = "refresh"


# ============================================================================
# FluidKit Metadata Models
# ============================================================================

class MutationEntry(BaseModel):
    """Base model for a mutation entry"""
    key: str
    args: Dict[str, Any]
    data: Any
    mutation_type: MutationType

class FluidKitMetadata(BaseModel):
    """Metadata for single-flight mutations and cookie instructions"""
    cookies: List[dict] = Field(default_factory=list)
    mutations: List[MutationEntry] = Field(default_factory=list)

class FieldAnnotation(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    base_type: BaseType | None = None
    container: ContainerType | None = None
    args: list['FieldAnnotation'] = Field(default_factory=list)
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
    parameters: List[ParameterMetadata]
    file_path: str | None = None
    module: str
    decorator_type: DecoratorType
    prerender_inputs: Optional[Any] = None
    prerender_dynamic: bool = False

# ============================================================================
# Response Models
# ============================================================================

T = TypeVar('T')

class QueryResponse(BaseModel, Generic[T]):
    """Response for @query and @prerender"""
    result: T

class BatchQueryResponse(BaseModel):
    """Response for @query.batch"""
    results: List[Any]

class CommandResponse(BaseModel, Generic[T]):
    """Response for @command and @form (success)"""
    model_config = ConfigDict(populate_by_name=True)

    result: T
    fluidkit_metadata: FluidKitMetadata = Field(default_factory=FluidKitMetadata, alias="__fluidkit")

class RedirectData(BaseModel):
    """Redirect information"""
    status: int = Field(ge=300, le=308)
    location: str

class RedirectResponse(BaseModel):
    """Response for @command/@form with redirect"""
    model_config = ConfigDict(populate_by_name=True)

    redirect: RedirectData
    fluidkit_metadata: FluidKitMetadata = Field(default_factory=FluidKitMetadata, alias="__fluidkit")

# ============================================================================
# Error Models
# ============================================================================

class FluidKitErrorDetails(BaseModel):
    """Error details for development mode"""
    type: str
    traceback: str

class UnhandledErrorResponse(BaseModel):
    """Response for unhandled exceptions in dev mode"""
    message: str
    error_details: FluidKitErrorDetails = Field(alias="__fluidkit_error")
    

# ============================================================================
# Request Models (for endpoints)
# ============================================================================

class FileUploadInfo(BaseModel):
    """Metadata for file uploads (not the file itself)"""
    filename: str
    content_type: str
    size: int

# ============================================================================
# Helper Functions
# ============================================================================

def create_query_response(result: Any) -> QueryResponse:
    """Create a query response"""
    return QueryResponse(result=result)

def create_batch_query_response(results: List[Any]) -> BatchQueryResponse:
    """Create a batch query response"""
    return BatchQueryResponse(results=results)

def create_command_response(
    result: Any,
    mutations: List[MutationEntry] = None,
    cookies: List[dict] = None,
) -> CommandResponse:
    """Create a command response with optional mutations and cookie instructions"""
    metadata = FluidKitMetadata(mutations=mutations or [], cookies=cookies or [])
    return CommandResponse(result=result, __fluidkit=metadata)

def create_redirect_response(
    status: int,
    location: str,
    cookies: List[dict] = None,
) -> RedirectResponse:
    redirect_data = RedirectData(status=status, location=location)
    metadata = FluidKitMetadata(cookies=cookies or [])
    return RedirectResponse(redirect=redirect_data, __fluidkit=metadata)

def create_error_response(e: Exception | None = None, message: str | None = None, *, dev: bool = False) -> UnhandledErrorResponse:
    """Create an error response, including details in development mode"""
    if e is not None and dev:
        import traceback
        return UnhandledErrorResponse(
            message=str(e),
            __fluidkit_error=FluidKitErrorDetails(
                type=type(e).__name__,
                traceback=traceback.format_exc()
            )
        )
    return UnhandledErrorResponse(message=message or "An unexpected error occurred")
