import inspect
import json
import logging
import uuid
from collections.abc import Callable
from datetime import date, datetime
from typing import Any, Literal, Union, get_args, get_origin

from fastapi import Request
from fastapi.responses import JSONResponse

from fluidkit.context import set_request_event
from fluidkit.models import (
    BaseType,
    CommandResponse,
    ContainerType,
    DecoratorType,
    FieldAnnotation,
    FunctionMetadata,
    ParameterMetadata,
    QueryResponse,
    RedirectResponse,
)
from fluidkit.types import Cookies, FileUpload, RequestEvent

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
    if get_origin(annotation) is Union:
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return annotation


# ── Metadata extraction ───────────────────────────────────────────────────────


def extract_metadata(func: Callable, decorator_type: DecoratorType):
    sig = inspect.signature(func)

    parameters = []
    request_param_name = None

    for param_name, param in sig.parameters.items():
        if param.annotation is RequestEvent:
            request_param_name = param_name
            continue

        if decorator_type in (DecoratorType.QUERY, DecoratorType.COMMAND, DecoratorType.PRERENDER):
            if normalize_types(param.annotation).base_type is BaseType.FILE:
                logger.warning(
                    "@%s '%s': parameter '%s' is FileUpload — file uploads are only supported in @form.",
                    decorator_type.value,
                    func.__name__,
                    param_name,
                )

        parameters.append(
            ParameterMetadata(
                name=param.name,
                default=param.default,
                annotation=normalize_types(param.annotation),
                required=param.default is inspect.Parameter.empty,
            )
        )

    metadata = FunctionMetadata(
        name=func.__name__,
        parameters=parameters,
        docstring=func.__doc__,
        module=func.__module__,
        decorator_type=decorator_type,
        file_path=inspect.getsourcefile(func),
        return_annotation=normalize_types(sig.return_annotation),
    )

    return metadata, request_param_name, sig


# ── Request handling ──────────────────────────────────────────────────────────


def setup_request_context(request: Request, allow_set_cookies: bool):
    cookies = Cookies(allow_set=allow_set_cookies, request_cookies=request.cookies)
    request_event = RequestEvent(locals={}, cookies=cookies)
    token = set_request_event(request_event)
    return request_event, cookies, token


def inject_request_if_needed(sig, args, kwargs, request_param_name, request_event):
    if request_param_name:
        bound = sig.bind_partial(*args, **kwargs)
        if request_param_name not in bound.arguments:
            kwargs[request_param_name] = request_event
    return kwargs


# ── Form parsing ──────────────────────────────────────────────────────────────


def _inject_file_at_path(data: dict, path: str, file) -> None:
    parts = []
    i = 0
    while i < len(path):
        if path[i] == "[":
            end = path.index("]", i)
            parts.append(int(path[i + 1 : end]))
            i = end + 1
            if i < len(path) and path[i] == ".":
                i += 1
        elif path[i] == ".":
            i += 1
        else:
            end = len(path)
            for sep in (".", "["):
                pos = path.find(sep, i)
                if pos != -1:
                    end = min(end, pos)
            parts.append(path[i:end])
            i = end

    target = data
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = file


def _coerce_params(data: dict, sig: inspect.Signature) -> dict:
    from pydantic import BaseModel

    for param_name, param in sig.parameters.items():
        if param.annotation is RequestEvent or param_name not in data:
            continue

        value = data[param_name]
        unwrapped = _unwrap_optional(param.annotation)
        origin = get_origin(unwrapped)

        if isinstance(unwrapped, type) and issubclass(unwrapped, BaseModel) and isinstance(value, dict):
            data[param_name] = unwrapped(**value)

        elif origin is list and isinstance(value, list):
            inner_args = get_args(unwrapped)
            if inner_args and isinstance(inner_args[0], type) and issubclass(inner_args[0], BaseModel):
                data[param_name] = [inner_args[0](**v) if isinstance(v, dict) else v for v in value]

    return data


async def parse_request_data(request: Request, sig: inspect.Signature) -> dict:
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" not in content_type and "application/x-www-form-urlencoded" not in content_type:
        return _coerce_params(await request.json(), sig)

    form = await request.form()
    raw_data = form.get("__fluidkit_data")
    if raw_data is None:
        return _coerce_params(await request.json(), sig)

    data = json.loads(raw_data)
    for key in form:
        if key != "__fluidkit_data":
            _inject_file_at_path(data, key, form[key])
    return _coerce_params(data, sig)


# ── Response ──────────────────────────────────────────────────────────────────


def build_json_response(response_data: QueryResponse | CommandResponse | RedirectResponse):
    return JSONResponse(content=response_data.model_dump(by_alias=True))


def generate_route_path(metadata: FunctionMetadata) -> str:
    module = metadata.module
    if module == "__main__":
        return f"/remote/{metadata.name}"
    return f"/remote/{module.replace('.', '/')}/{metadata.name}"


# ── Type normalization ────────────────────────────────────────────────────────


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
            return FieldAnnotation(container=ContainerType.OPTIONAL, args=[normalize_types(non_none[0])])

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
        return FieldAnnotation(
            container=ContainerType.RECORD,
            args=[FieldAnnotation(base_type=BaseType.STRING), FieldAnnotation(base_type=BaseType.ANY)],
        )

    if inspect.isclass(py_type):
        return FieldAnnotation(custom_type=py_type.__name__, class_reference=py_type)

    return FieldAnnotation(base_type=BaseType.ANY)
