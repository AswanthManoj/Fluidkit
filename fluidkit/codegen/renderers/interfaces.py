import inspect
import logging
from enum import Enum
from pydantic import BaseModel
from typing import get_type_hints
from pydantic_core import PydanticUndefinedType

from fluidkit.utilities import normalize_types
from fluidkit.models import FieldAnnotation, BaseType
from fluidkit.codegen.ts import TSWriter, annotation_to_ts


logger = logging.getLogger(__name__)


_BROWSER_RESERVED = {
    "Request", "Response", "URL", "Node", "Comment",
    "Blob", "FormData", "Headers", "Cache", "Storage",
    "File", "Event", "Location", "Error", "Date", "Image", "Array"
}


def render_class(cls: type) -> str:
    prefix = ""
    if cls.__name__ in _BROWSER_RESERVED:
        logger.warning(
            "Pydantic model named '%s' conflicts with a browser-native TypeScript type — "
            "generated interface may cause type collisions in client code. "
            "Consider renaming the model.",
            cls.__name__
        )
        prefix = (
            f"// ⚠️ WARNING: '{cls.__name__}' conflicts with a browser-native TypeScript type.\n"
            f"// This may cause type collisions in client code. Consider renaming this model.\n"
        )
    if issubclass(cls, Enum):
        return prefix + _render_enum(cls)
    if issubclass(cls, BaseModel):
        return prefix + _render_interface(cls)
    logger.warning("Unsupported class type for rendering: %s", cls.__name__)
    return ""


def _render_interface(cls: type) -> str:
    fields = cls.model_fields if hasattr(cls, "model_fields") else {}

    try:
        hints = get_type_hints(cls)
    except Exception:
        logger.warning("Failed to get type hints for %s, falling back to any", cls.__name__)
        hints = {}

    w = TSWriter()
    with w.block(f"export interface {cls.__name__} {{"):
        for field_name, field_info in fields.items():
            py_type = hints.get(field_name)
            ann = normalize_types(py_type) if py_type else FieldAnnotation(base_type=BaseType.ANY)
            optional = "?" if _has_default(field_info) else ""
            w.line(f"{field_name}{optional}: {annotation_to_ts(ann)};")

    return w.render()


def _render_enum(cls: type) -> str:
    w = TSWriter()
    with w.block(f"export enum {cls.__name__} {{"):
        for member in cls:
            value = member.value
            if isinstance(value, str):
                w.line(f'{member.name} = "{value}",')
            else:
                w.line(f"{member.name} = {value},")

    return w.render()


def _has_default(field_info) -> bool:
    if not hasattr(field_info, "default"):
        return False
    return not isinstance(field_info.default, PydanticUndefinedType)
