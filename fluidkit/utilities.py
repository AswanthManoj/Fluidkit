import json
import uuid
import inspect
import logging
from fastapi import Request
from datetime import datetime, date
from fastapi.responses import JSONResponse
from typing import Callable, Any, Union, Literal, get_args, get_origin

from fluidkit.types import *
from fluidkit.models import *
from fluidkit.context import set_request_event


logger = logging.getLogger(__name__)


_PRIMITIVES = {
    str: BaseType.STRING,
    int: BaseType.NUMBER,
    float: BaseType.NUMBER,
    bool: BaseType.BOOLEAN,
}

_SCALARS = {
    date: BaseType.STRING,
    datetime: BaseType.STRING,
    uuid.UUID: BaseType.STRING,
}


def _unwrap_optional(annotation) -> Any:
    """If annotation is Optional[X] (i.e. Union[X, None] with one non-None), return X. Otherwise return as-is."""
    if get_origin(annotation) is Union:
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return annotation


def _warn_form_param(func_name: str, param_name: str, annotation) -> None:
    """Emit warnings for form parameters that won't serialize well."""
    from pydantic import BaseModel

    unwrapped = _unwrap_optional(annotation)
    origin = get_origin(unwrapped)

    if isinstance(unwrapped, type) and issubclass(unwrapped, BaseModel):
        logger.warning(
            "@form '%s': parameter '%s' is a Pydantic model — "
            "form fields only support flat primitives, files, and lists of those. "
            "Consider using @command for complex model parameters.",
            func_name, param_name
        )
    elif origin is dict:
        logger.warning(
            "@form '%s': parameter '%s' is a dict — "
            "form fields do not support dict types. "
            "Consider using @command instead.",
            func_name, param_name
        )
    elif origin is list:
        inner_args = get_args(unwrapped)
        if inner_args and isinstance(inner_args[0], type) and issubclass(inner_args[0], BaseModel):
            logger.warning(
                "@form '%s': parameter '%s' is list[%s] — "
                "form fields only support lists of primitives or FileUpload. "
                "Consider using @command instead.",
                func_name, param_name, inner_args[0].__name__
            )

    if get_origin(annotation) is Union:
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        if len(non_none) > 1:
            logger.warning(
                "@form '%s': parameter '%s' has Union type %s — "
                "form coercion is ambiguous for Union types, value will be returned as raw string. "
                "Consider wrapping the Union in a Pydantic model and using @command instead.",
                func_name, param_name, annotation
            )


def extract_metadata(func: Callable, decorator_type: DecoratorType):
    sig = inspect.signature(func)

    parameters = []
    filtered_params = []
    request_param_name = None

    for param_name, param in sig.parameters.items():
        if param.annotation is RequestEvent:
            request_param_name = param_name
            continue

        if decorator_type == DecoratorType.FORM:
            _warn_form_param(func.__name__, param_name, param.annotation)

        if decorator_type in (DecoratorType.QUERY, DecoratorType.COMMAND, DecoratorType.PRERENDER):
            if normalize_types(param.annotation).base_type is BaseType.FILE:
                logger.warning(
                    "@%s '%s': parameter '%s' is FileUpload — "
                    "file uploads are only supported in @form. "
                    "Consider changing the decorator to @form.",
                    decorator_type.value, func.__name__, param_name
                )

        parameters.append(
            ParameterMetadata(
                name=param.name,
                default=param.default,
                annotation=normalize_types(param.annotation),
                required=param.default is inspect.Parameter.empty
            )
        )
        filtered_params.append(param)

    metadata = FunctionMetadata(
        name=func.__name__,
        parameters=parameters,
        docstring=func.__doc__,
        module=func.__module__,
        decorator_type=decorator_type,
        file_path=inspect.getsourcefile(func),
        return_annotation=normalize_types(sig.return_annotation)
    )

    return metadata, request_param_name, filtered_params, sig


def setup_request_context(request: Request, allow_set_cookies: bool):
    """Setup request event and return cleanup token"""
    cookies = Cookies(
        allow_set=allow_set_cookies,
        request_cookies=request.cookies
    )
    request_event = RequestEvent(locals={}, cookies=cookies)
    token = set_request_event(request_event)
    return request_event, cookies, token

def generate_route_path(metadata: FunctionMetadata) -> str:
    module = metadata.module
    if module == '__main__':
        return f"/remote/{metadata.name}"
    module_path = module.replace('.', '/')
    return f"/remote/{module_path}/{metadata.name}"

def build_json_response(response_data: QueryResponse|CommandResponse|RedirectResponse):
    """Build JSONResponse with cookies applied"""
    return JSONResponse(content=response_data.model_dump(by_alias=True))

def inject_request_if_needed(sig, args, kwargs, request_param_name, request_event):
    """Inject request_event if param exists and not already provided"""
    if request_param_name:
        bound = sig.bind_partial(*args, **kwargs)
        if request_param_name not in bound.arguments:
            kwargs[request_param_name] = request_event
    return kwargs

async def parse_request_data(request: Request, sig: inspect.Signature) -> dict:
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" not in content_type and "application/x-www-form-urlencoded" not in content_type:
        return await request.json()

    form = await request.form()
    parsed = {}

    for param_name, param in sig.parameters.items():
        if param.annotation is RequestEvent:
            continue

        unwrapped = _unwrap_optional(param.annotation)
        origin = get_origin(unwrapped)

        if origin is list:
            values = form.getlist(param_name)
            if not values:
                continue
            inner_args = get_args(unwrapped)
            inner_type = inner_args[0] if inner_args else str
            parsed[param_name] = [_coerce_form_value(v, inner_type) for v in values]
        else:
            value = form.get(param_name)
            if value is None:
                continue
            parsed[param_name] = _coerce_form_value(value, unwrapped)

    return parsed


def _coerce_form_value(value: Any, annotation: type) -> Any:
    from pydantic import BaseModel
    from fastapi import UploadFile as FastAPIUploadFile

    if isinstance(value, FastAPIUploadFile):
        return value

    if not isinstance(value, str):
        return value

    origin = get_origin(annotation)

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation(**json.loads(value))

    if origin in (list, dict):
        return json.loads(value)

    if annotation is int:
        return int(value)
    if annotation is float:
        return float(value)
    if annotation is bool:
        return value.lower() in ('true', '1', 'yes')

    return value


def normalize_types(py_type: Any) -> FieldAnnotation:
    if py_type is inspect.Parameter.empty:
        return FieldAnnotation(base_type=BaseType.ANY)

    if py_type is None:
        return FieldAnnotation(base_type=BaseType.VOID)

    if py_type is type(None):
        return FieldAnnotation(base_type=BaseType.NULL)

    if py_type in _PRIMITIVES:
        return FieldAnnotation(base_type=_PRIMITIVES[py_type])

    if py_type in _SCALARS:
        return FieldAnnotation(base_type=_SCALARS[py_type])

    if py_type is FileUpload:
        return FieldAnnotation(base_type=BaseType.FILE, class_reference=FileUpload)

    args = get_args(py_type)
    origin = get_origin(py_type)

    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        has_none = type(None) in args

        if has_none and len(non_none) == 1:
            return FieldAnnotation(
                container=ContainerType.OPTIONAL,
                args=[normalize_types(non_none[0])]
            )

        union_args = [normalize_types(a) for a in non_none]
        result = FieldAnnotation(container=ContainerType.UNION, args=union_args)
        if has_none:
            return FieldAnnotation(container=ContainerType.OPTIONAL, args=[result])
        return result

    if origin is list:
        inner = normalize_types(args[0]) if args else FieldAnnotation(base_type=BaseType.ANY)
        return FieldAnnotation(container=ContainerType.ARRAY, args=[inner])

    if origin is dict:
        k = normalize_types(args[0]) if args else FieldAnnotation(base_type=BaseType.ANY)
        v = normalize_types(args[1]) if len(args) > 1 else FieldAnnotation(base_type=BaseType.ANY)
        return FieldAnnotation(container=ContainerType.RECORD, args=[k, v])

    if origin is tuple:
        return FieldAnnotation(container=ContainerType.TUPLE, args=[normalize_types(a) for a in args])

    if origin is Literal:
        return FieldAnnotation(container=ContainerType.LITERAL, literal_values=list(args))

    if py_type is dict:
        return FieldAnnotation(container=ContainerType.RECORD, args=[
            FieldAnnotation(base_type=BaseType.STRING),
            FieldAnnotation(base_type=BaseType.ANY)
        ])

    if inspect.isclass(py_type):
        return FieldAnnotation(custom_type=py_type.__name__, class_reference=py_type)

    return FieldAnnotation(base_type=BaseType.ANY)
