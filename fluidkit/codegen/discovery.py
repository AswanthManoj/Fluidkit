import logging
from enum import Enum
from pydantic import BaseModel
from typing import get_type_hints

from fluidkit.utilities import normalize_types
from fluidkit.models import FieldAnnotation, FunctionMetadata, BaseType


logger = logging.getLogger(__name__)


def collect_classes(ann: FieldAnnotation, found: dict):
    if ann.class_reference is not None and ann.base_type is not BaseType.FILE:
        found[ann.custom_type] = ann.class_reference
    for arg in ann.args:
        collect_classes(arg, found)


def discover_all_classes(functions: list[FunctionMetadata]) -> dict[str, type]:
    found = {}

    for fn in functions:
        collect_classes(fn.return_annotation, found)
        for param in fn.parameters:
            collect_classes(param.annotation, found)

    queue = list(found.values())
    while queue:
        cls = queue.pop()

        if issubclass(cls, Enum):
            continue

        if issubclass(cls, BaseModel):
            try:
                hints = get_type_hints(cls)
            except Exception:
                logger.warning("Failed to get type hints for %s, skipping nested discovery", cls.__name__)
                continue

            for field_type in hints.values():
                nested = {}
                try:
                    collect_classes(normalize_types(field_type), nested)
                except Exception:
                    logger.warning("Failed to normalize type %s in %s", field_type, cls.__name__)
                    continue

                for name, ref in nested.items():
                    if name not in found:
                        found[name] = ref
                        queue.append(ref)

    return found
