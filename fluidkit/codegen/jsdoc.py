"""
JSDoc generation for .remote.ts files.

Generates IDE-visible documentation with Svelte usage examples
for each generated remote function, based on decorator type,
parameters, and return type analysis.
"""

import re
from enum import StrEnum

from fluidkit.models import (
    BaseType,
    ContainerType,
    DecoratorType,
    FieldAnnotation,
    FunctionMetadata,
)
from fluidkit.codegen.ts import TSWriter, annotation_to_ts


_INPUT_TYPE_MAP = {
    BaseType.FILE: "file",
    BaseType.STRING: "text",
    BaseType.NUMBER: "number",
    BaseType.BOOLEAN: "checkbox",
}

class ReturnShape(StrEnum):
    ANY = "any"
    VOID = "void"
    RECORD = "record"
    ARRAY_PYDANTIC = "array_pydantic"
    ARRAY_PRIMITIVE = "array_primitive"
    SINGLE_PYDANTIC = "single_pydantic"
    SINGLE_PRIMITIVE = "single_primitive"
    OPTIONAL_PYDANTIC = "optional_pydantic"
    OPTIONAL_PRIMITIVE = "optional_primitive"
    
_STRIP_PREFIXES = ("get_", "fetch_", "list_", "find_", "load_", "search_")


def _is_pydantic(ref) -> bool:
    from pydantic import BaseModel
    return ref is not None and isinstance(ref, type) and issubclass(ref, BaseModel)


def _detect_return_shape(ann: FieldAnnotation) -> ReturnShape:
    if ann.base_type in (BaseType.VOID, BaseType.NULL):
        return ReturnShape.VOID

    if ann.base_type in (BaseType.STRING, BaseType.NUMBER, BaseType.BOOLEAN):
        return ReturnShape.SINGLE_PRIMITIVE

    if ann.container == ContainerType.ARRAY and ann.args:
        if _is_pydantic(ann.args[0].class_reference):
            return ReturnShape.ARRAY_PYDANTIC
        return ReturnShape.ARRAY_PRIMITIVE

    if ann.container == ContainerType.OPTIONAL and ann.args:
        if _is_pydantic(ann.args[0].class_reference):
            return ReturnShape.OPTIONAL_PYDANTIC
        return ReturnShape.OPTIONAL_PRIMITIVE

    if ann.container == ContainerType.RECORD:
        return ReturnShape.RECORD

    if _is_pydantic(ann.class_reference):
        return ReturnShape.SINGLE_PYDANTIC

    return ReturnShape.ANY


def _to_relative_path(file_path: str) -> str:
    path = file_path.replace("\\", "/")
    idx = path.find("src/")
    if idx != -1:
        return path[idx:]
    return path


def _file_to_import_path(file_path: str) -> str:
    path = _to_relative_path(file_path).removesuffix(".py")
    if path.startswith("src/lib/"):
        return "$lib/" + path[8:] + ".remote"
    if path.startswith("src/"):
        return "$" + path[4:] + ".remote"
    return path + ".remote"


def _format_label(field_name: str) -> str:
    if "_" not in field_name and any(c.isupper() for c in field_name):
        parts = re.sub(r"([a-z])([A-Z])", r"\1 \2", field_name).split()
        return " ".join(p.capitalize() for p in parts)
    return " ".join(p.capitalize() for p in field_name.split("_"))


def _derive_variable_name(fn: FunctionMetadata) -> str:
    ann = fn.return_annotation

    inner = None
    if ann.container in (ContainerType.ARRAY, ContainerType.OPTIONAL) and ann.args:
        inner = ann.args[0]
    elif ann.class_reference:
        inner = ann

    if inner and inner.class_reference:
        cls_name = inner.class_reference.__name__
        return re.sub(r"([a-z])([A-Z])", r"\1_\2", cls_name).lower()

    name = fn.name
    for prefix in _STRIP_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break

    if name.endswith("s") and len(name) > 3:
        name = name[:-1]

    return name or "item"


def _get_display_fields(ann: FieldAnnotation) -> list[str]:
    if ann.container in (ContainerType.ARRAY, ContainerType.OPTIONAL) and ann.args:
        ref = ann.args[0].class_reference
    else:
        ref = ann.class_reference
    if not _is_pydantic(ref) or not hasattr(ref, "model_fields"):
        return []
    return list(ref.model_fields.keys())


def _format_call(fn: FunctionMetadata) -> str:
    param_names = [p.name for p in fn.parameters]
    if not param_names:
        return f"{fn.name}()"
    if len(param_names) == 1:
        return f"{fn.name}({param_names[0]})"
    return f"{fn.name}({{ {', '.join(param_names)} }})"


def _render_query_example(fn: FunctionMetadata, import_path: str) -> list[str]:
    shape = _detect_return_shape(fn.return_annotation)
    var = _derive_variable_name(fn)
    fields = _get_display_fields(fn.return_annotation)
    call = _format_call(fn)

    needs_derived = (
        shape in (ReturnShape.SINGLE_PYDANTIC, ReturnShape.OPTIONAL_PYDANTIC, ReturnShape.OPTIONAL_PRIMITIVE)
    )

    lines = [
        " * ```svelte",
        " * <script>",
        f" *   import {{ {fn.name} }} from '{import_path}';",
    ]

    if needs_derived:
        lines += [" *", f" *   const {var} = $derived(await {call});"]

    lines += [" * </script>", " *"]

    if shape == ReturnShape.ARRAY_PYDANTIC and fields:
        lines += [f" * {{#each await {call} as {var}}}"]
        lines += [f" *   <p>{_format_label(f)}: {{{var}.{f}}}</p>" for f in fields]
        lines += [" * {/each}"]

    elif shape == ReturnShape.ARRAY_PRIMITIVE:
        lines += [
            f" * {{#each await {call} as {var}}}",
            f" *   <span>{{{var}}}</span>",
            " * {/each}",
        ]

    elif shape == ReturnShape.SINGLE_PYDANTIC and fields:
        lines += [f" * <p>{_format_label(f)}: {{{var}.{f}}}</p>" for f in fields]

    elif shape == ReturnShape.OPTIONAL_PYDANTIC and fields:
        lines += [f" * {{#if {var}}}"]
        lines += [f" *   <p>{_format_label(f)}: {{{var}.{f}}}</p>" for f in fields]
        lines += [
            " * {:else}",
            f" *   <p>{_format_label(var)} not found</p>",
            " * {/if}",
        ]

    elif shape == ReturnShape.OPTIONAL_PRIMITIVE:
        lines += [
            f" * {{#if {var}}}",
            f" *   <p>{{{var}}}</p>",
            " * {:else}",
            f" *   <p>{_format_label(var)} not found</p>",
            " * {/if}",
        ]

    elif shape == ReturnShape.RECORD:
        lines += [
            f" * {{#each Object.entries(await {call}) as [key, value]}}",
            " *   <p>{key}: {value}</p>",
            " * {/each}",
        ]

    elif shape == ReturnShape.SINGLE_PRIMITIVE:
        lines += [f" * <p>{{await {call}}}</p>"]

    else:
        lines += [f" * {{await {call}}}"]

    lines += [" * ```"]
    return lines


def _render_command_example(fn: FunctionMetadata, import_path: str) -> list[str]:
    call = _format_call(fn)
    label = fn.name.replace("_", " ").title()
    ann = fn.return_annotation
    is_void = (
        ann.base_type in (BaseType.VOID, BaseType.NULL, BaseType.ANY, None)
        and ann.container is None
        and ann.class_reference is None
    )

    lines = [
        " * ```svelte",
        " * <script>",
        f" *   import {{ {fn.name} }} from '{import_path}';",
        " * </script>",
        " *",
    ]

    if is_void:
        lines += [
            f" * <button onclick={{async () => await {call}}}>",
            f" *   {label}",
            " * </button>",
        ]
    else:
        lines += [
            f" * <button onclick={{async () => {{",
            f" *   const result = await {call};",
            " * }}>",
            f" *   {label}",
            " * </button>",
        ]

    lines += [" * ```"]
    return lines


def _render_form_example(fn: FunctionMetadata, import_path: str) -> list[str]:
    has_file = any(p.annotation.base_type == BaseType.FILE for p in fn.parameters)

    lines = [
        " * ```svelte",
        " * <script>",
        f" *   import {{ {fn.name} }} from '{import_path}';",
        " * </script>",
        " *",
    ]

    form_attrs = f"{{...{fn.name}}}"
    if has_file:
        form_attrs += ' enctype="multipart/form-data"'

    lines += [f" * <form {form_attrs}>"]

    for p in fn.parameters:
        input_type = _INPUT_TYPE_MAP.get(p.annotation.base_type, "text")
        lines += [f" *   <input {{...{fn.name}.fields.{p.name}.as('{input_type}')}} />"]

    lines += [
        " *   <button>Submit</button>",
        " * </form>",
        " * ```",
    ]
    return lines


def render_jsdoc(w: TSWriter, fn: FunctionMetadata) -> None:
    import_path = _file_to_import_path(fn.file_path) if fn.file_path else fn.module
    decorator_name = fn.decorator_type.value
    if fn.decorator_type == DecoratorType.QUERY_BATCH:
        decorator_name = "query"

    lines = ["/**"]

    if fn.docstring:
        for doc_line in fn.docstring.strip().splitlines():
            lines += [f" * {doc_line.strip()}"]

    ret_ts = annotation_to_ts(fn.return_annotation)
    if ret_ts not in ("any", "void"):
        lines += [" *", f" * @returns `{ret_ts}`"]

    lines += [" *", " * ---"]

    source_path = _to_relative_path(fn.file_path) if fn.file_path else fn.module
    if fn.file_path:
        py_filename = "./" + fn.file_path.replace("\\", "/").rsplit("/", 1)[-1]
        lines += [f" * @see [`{source_path}` . `@{decorator_name}`]({py_filename})"]
    
    lines += [
        f" * @see [Fluidkit Docs #{decorator_name}](https://fluidkit.github.io/docs/{decorator_name})",
        f" *",
        f" * ---"
    ]

    lines += [" *", " * @example"]

    if fn.decorator_type in (DecoratorType.QUERY, DecoratorType.QUERY_BATCH, DecoratorType.PRERENDER):
        lines += _render_query_example(fn, import_path)
    elif fn.decorator_type == DecoratorType.COMMAND:
        lines += _render_command_example(fn, import_path)
    elif fn.decorator_type == DecoratorType.FORM:
        lines += _render_form_example(fn, import_path)

    lines += [" */"]

    for line in lines:
        w.line(line)
