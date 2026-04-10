import logging
from pathlib import Path

from fluidkit.codegen.renderers import render_class
from fluidkit.codegen.remote import generate_remote_files
from fluidkit.codegen.discovery import discover_all_classes
from fluidkit.models import BaseType, FieldAnnotation, FunctionMetadata
from fluidkit.codegen.ts import GENERATED_FILE_WARNING, TSWriter, module_to_namespace


logger = logging.getLogger(__name__)


def _warn_untyped(functions: list[FunctionMetadata]):
    for fn in functions:
        untyped = [p.name for p in fn.parameters if p.annotation.base_type is BaseType.ANY]
        if untyped:
            logger.warning(
                "%s.%s has unannotated parameters: %s — generated types will be 'any'",
                fn.module,
                fn.name,
                ", ".join(untyped),
            )


def _has_custom_types(metadata: FunctionMetadata) -> bool:
    def _check(ann: FieldAnnotation) -> bool:
        if ann.class_reference is not None:
            return True
        return any(_check(a) for a in ann.args)

    return _check(metadata.return_annotation) or any(_check(p.annotation) for p in metadata.parameters)


def _write_config_ts(base_url: str, schema_output: str) -> None:
    config_path = Path(schema_output) / "config.ts"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        f'{GENERATED_FILE_WARNING}'
        f'import {{ Agent, fetch as _undici_fetch }} from \'undici\';\n\n'
        f'export const BASE_URL = "{base_url}";\n\n'
        f'const _fk_agent = new Agent({{\n'
        f'  connections: null,\n'
        f'  pipelining: 1,\n'
        f'  keepAliveTimeout: 30_000,\n'
        f'  keepAliveMaxTimeout: 60_000,\n'
        f'}});\n\n'
        f'export function _fk_fetch(url: string, init: object): Promise<Response> {{\n'
        f'  return _undici_fetch(url, {{ ...init, dispatcher: _fk_agent }}) as unknown as Response;\n'
        f'}}\n',
        encoding="utf-8",
    )


def _write_hooks_server_ts() -> None:
    import hashlib
    from fluidkit.hooks import hooks
    from fluidkit.registry import fluidkit_registry

    hooks_path = Path("src/hooks.server.ts")

    if not hooks.has_hooks:
        if hooks_path.exists():
            existing = hooks_path.read_text(encoding="utf-8")
            if existing.startswith(GENERATED_FILE_WARNING):
                hooks_path.unlink()
                logger.debug("removed src/hooks.server.ts — no hooks registered")
        return

    signed = fluidkit_registry.signed
    sign_import = "import { signRequest } from '$fluidkit/auth';\n" if signed else ""
    sign_header = "\n          'X-FluidKit-Token': signRequest()," if signed else ""

    content = (
        f"{GENERATED_FILE_WARNING}"
        "import type { Handle } from '@sveltejs/kit';\n"
        "import { error, redirect } from '@sveltejs/kit';\n"
        "import { BASE_URL, _fk_fetch } from '$fluidkit/config';\n"
        f"{sign_import}"
        "\n"
        "export const handle: Handle = async ({ event, resolve }) => {\n"
        "  const _fk_path = new URL(event.request.url).pathname;\n"
        "  if (!_fk_path.startsWith('/remote/') && _fk_path !== '/__fk_hooks__') {\n"
        "    try {\n"
        "      const _fk_res = await _fk_fetch(`${BASE_URL}/__fk_hooks__`, {\n"
        "        method: 'POST',\n"
        "        headers: {\n"
        "          'Content-Type': 'application/json',"
        f"{sign_header}\n"
        "        },\n"
        "        body: JSON.stringify({\n"
        "          url: event.request.url,\n"
        "          method: event.request.method,\n"
        "          headers: Object.fromEntries(event.request.headers),\n"
        "          cookies: event.cookies.getAll(),\n"
        "        }),\n"
        "      });\n"
        "      const _fk_body = await _fk_res.json();\n"
        "      if (_fk_body.redirect) {\n"
        "        redirect(_fk_body.redirect.status, _fk_body.redirect.location);\n"
        "      }\n"
        "      if (_fk_body.error) {\n"
        "        error(_fk_body.error.status, _fk_body.error.message);\n"
        "      }\n"
        "      for (const { name, value, ...opts } of _fk_body.__fk_cookies ?? []) {\n"
        "        event.cookies.set(name, value, { path: '/', ...opts });\n"
        "      }\n"
        "      Object.assign(event.locals, _fk_body.__fk_locals ?? {});\n"
        "    } catch (_fk_err) {\n"
        "      if (_fk_err instanceof Response) throw _fk_err;\n"
        "      // silent — do not crash the page request\n"
        "    }\n"
        "  }\n"
        "  return resolve(event);\n"
        "};\n"
    )

    if hooks_path.exists():
        existing = hooks_path.read_text(encoding="utf-8")
        if hashlib.sha256(existing.encode()).hexdigest() == hashlib.sha256(content.encode()).hexdigest():
            return
        logger.warning(
            "src/hooks.server.ts exists and differs from FluidKit's generated version — overwriting. "
            "If you have custom handle logic, use SvelteKit's sequence() helper."
        )

    hooks_path.parent.mkdir(parents=True, exist_ok=True)
    hooks_path.write_text(content, encoding="utf-8")
    logger.debug("generated src/hooks.server.ts")


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
        functions_for_file = {k: v for k, v in registry.functions.items() if v.file_path == metadata.file_path}
        if not functions_for_file:
            remote_ts = Path(metadata.file_path.replace(".py", ".remote.ts"))
            remote_ts.unlink(missing_ok=True)
        else:
            generate_remote_files(functions_for_file, signed=registry.signed)

    if _has_custom_types(metadata):
        schema_ts = build_schema_ts(list(registry.functions.values()))
        schema_path = Path(schema_output) / "schema.ts"
        schema_path.parent.mkdir(parents=True, exist_ok=True)
        schema_path.write_text(schema_ts, encoding="utf-8")


def watch(registry, base_url: str, schema_output: str):
    def _on_change(event: dict):
        _run_codegen(event["metadata"], registry, base_url, schema_output)

    registry.on_change(_on_change)


def generate(
    functions: dict[str, FunctionMetadata],
    base_url: str = "http://localhost:8000",
    schema_output: str = "src/lib/fluidkit",
    signed: bool = True,
) -> None:
    """
    Generate all FluidKit artifacts:
    - $fluidkit/config.ts with BASE_URL
    - .remote.ts files colocated with Python source
    - $fluidkit/schema.ts with all Pydantic model interfaces
    """
    _write_config_ts(base_url, schema_output)
    generate_remote_files(functions, signed=signed)
    schema_ts = build_schema_ts(list(functions.values()))
    schema_path = Path(schema_output) / "schema.ts"
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(schema_ts, encoding="utf-8")
    logger.debug("generated %s", schema_path)
    _write_hooks_server_ts()
