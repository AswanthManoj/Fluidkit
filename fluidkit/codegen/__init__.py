import logging
from typing import Dict
from pathlib import Path
from fluidkit.codegen.renderers import render_class
from fluidkit.codegen.remote import generate_remote_files
from fluidkit.codegen.discovery import discover_all_classes
from fluidkit.models import FunctionMetadata, BaseType, FieldAnnotation
from fluidkit.codegen.ts import GENERATED_FILE_WARNING, TSWriter, module_to_namespace


logger = logging.getLogger(__name__)


def _warn_untyped(functions: list[FunctionMetadata]):
    for fn in functions:
        untyped = [p.name for p in fn.parameters if p.annotation.base_type is BaseType.ANY]

        # This is obvious from the return type in typescript, so we don't need to warn about it.
        # if fn.return_annotation.base_type is BaseType.ANY:
        #     untyped.append("return")
        
        if untyped:
            logger.warning(
                "%s.%s has unannotated parameters: %s — generated types will be 'any'",
                fn.module, fn.name, ", ".join(untyped)
            )


def _has_custom_types(metadata: FunctionMetadata) -> bool:
    def _check(ann: FieldAnnotation) -> bool:
        if ann.class_reference is not None:
            return True
        return any(_check(a) for a in ann.args)
    return _check(metadata.return_annotation) or any(_check(p.annotation) for p in metadata.parameters)


def build_schema_ts(functions: list[FunctionMetadata]) -> str:
    _warn_untyped(functions)
    all_classes = discover_all_classes(functions)
    if not all_classes:
        return GENERATED_FILE_WARNING + "// no models found\n"

    by_module: dict[str, list[type]] = {}
    for cls in all_classes.values():
        by_module.setdefault(cls.__module__, []).append(cls)

    w = TSWriter()
    w.line(GENERATED_FILE_WARNING)
    for module, classes in by_module.items():
        namespace = module_to_namespace(module)
        with w.block(f"export namespace {namespace} {{"):
            for cls in classes:
                ts = render_class(cls)
                if not ts:
                    continue
                for line in ts.splitlines():
                    w.line(line)
                w.blank()

    return w.render()


def _run_codegen(metadata: FunctionMetadata, registry, base_url: str, schema_output: str):
    if metadata.file_path:
        functions_for_file = {
            k: v for k, v in registry.functions.items()
            if v.file_path == metadata.file_path
        }
        if not functions_for_file:
            remote_ts = Path(metadata.file_path.replace(".py", ".remote.ts"))
            remote_ts.unlink(missing_ok=True)
        else:
            generate_remote_files(functions_for_file, base_url=base_url)

    if _has_custom_types(metadata):
        schema_ts = build_schema_ts(list(registry.functions.values()))
        schema_path = Path(schema_output) / "schema.ts"
        schema_path.parent.mkdir(parents=True, exist_ok=True)
        schema_path.write_text(schema_ts, encoding="utf-8")


def watch(registry, base_url: str, schema_output: str):
    def _on_register(metadata: FunctionMetadata):
        _run_codegen(metadata, registry, base_url, schema_output)
    registry.on_register(_on_register)


def generate(
    functions: Dict[str, FunctionMetadata],
    base_url: str = "http://localhost:8000",
    schema_output: str = "src/lib/fluidkit",
) -> None:
    """
    Generate all FluidKit artifacts:
    - .remote.ts files colocated with Python source
    - $fluidkit/schema.ts with all Pydantic model interfaces
    """
    generate_remote_files(functions, base_url=base_url)
    schema_ts = build_schema_ts(list(functions.values()))
    schema_path = Path(schema_output) / "schema.ts"
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(schema_ts, encoding="utf-8")
    logger.debug("generated %s", schema_path)
