import json
import logging
from pathlib import Path

from fluidkit.utilities import generate_route_path
from fluidkit.codegen.ts import GENERATED_FILE_WARNING, TSWriter, annotation_to_ts, module_to_namespace
from fluidkit.models import ContainerType, DecoratorType, FieldAnnotation, FunctionMetadata, ParameterMetadata


logger = logging.getLogger(__name__)


def generate_remote_files(
    functions: dict[str, FunctionMetadata],
) -> None:
    by_file: dict[str, list[FunctionMetadata]] = {}
    for fn in functions.values():
        if fn.file_path:
            by_file.setdefault(fn.file_path, []).append(fn)

    for file_path, fns in by_file.items():
        content = render_remote_file(fns)
        if not content:
            continue
        out_path = file_path.replace(".py", ".remote.ts")
        Path(out_path).write_text(content, encoding="utf-8")
        logger.debug("generated %s", out_path)


def render_remote_file(functions: list[FunctionMetadata]) -> str:
    if not functions:
        return ""

    types = {f.decorator_type for f in functions}
    has_mutations = bool(types & {DecoratorType.COMMAND, DecoratorType.FORM})
    has_registrations = bool(types & {DecoratorType.QUERY, DecoratorType.QUERY_BATCH})
    custom_types = _collect_custom_types(functions)

    w = TSWriter()
    w.line(GENERATED_FILE_WARNING)
    _render_imports(w, types, has_mutations, has_registrations, custom_types)

    for fn in functions:
        w.blank()
        if fn.decorator_type == DecoratorType.QUERY:
            _render_query(w, fn)
        elif fn.decorator_type == DecoratorType.QUERY_BATCH:
            _render_query_batch(w, fn)
        elif fn.decorator_type == DecoratorType.PRERENDER:
            _render_prerender(w, fn)
        elif fn.decorator_type == DecoratorType.FORM:
            _render_form(w, fn)
        elif fn.decorator_type == DecoratorType.COMMAND:
            _render_command(w, fn)

    if has_registrations:
        w.blank()
        for fn in functions:
            if fn.decorator_type in (DecoratorType.QUERY, DecoratorType.QUERY_BATCH):
                _render_registration(w, fn)

    return w.render()


def _collect_custom_types(functions: list[FunctionMetadata]) -> dict[str, str]:
    found: dict[str, str] = {}

    def _collect(ann: FieldAnnotation):
        if ann.custom_type and ann.custom_type != "File" and ann.class_reference:
            found[ann.custom_type] = ann.class_reference.__module__
        for arg in ann.args:
            _collect(arg)

    for fn in functions:
        _collect(fn.return_annotation)
        for param in fn.parameters:
            _collect(param.annotation)

    return found


def _render_imports(
    w: TSWriter,
    types: set[DecoratorType],
    has_mutations: bool,
    has_registrations: bool,
    custom_types: dict[str, str],
) -> None:
    has_forms = bool(types & {DecoratorType.FORM})
    kit_imports = ["error"]
    if has_forms:
        kit_imports.append("redirect")
    w.line(f"import {{ {', '.join(kit_imports)} }} from '@sveltejs/kit';")

    def _import_name(t: DecoratorType) -> str:
        if t == DecoratorType.PRERENDER:
            return "prerender"
        if t == DecoratorType.QUERY_BATCH:
            return "query"
        return t.value

    app_imports = sorted({_import_name(t) for t in types}) + ["getRequestEvent"]
    w.line(f"import {{ {', '.join(app_imports)} }} from '$app/server';")

    registry_imports = []
    if has_mutations:
        registry_imports.append("getRemoteFunction")
    if has_registrations:
        registry_imports.append("registerRemoteFunction")
    if has_forms:
        registry_imports.extend(["extractFiles", "hasFiles"])
    if registry_imports:
        w.line(f"import {{ {', '.join(sorted(registry_imports))} }} from '$fluidkit/registry';")

    w.line("import { BASE_URL } from '$fluidkit/config';")
    w.line("import { signRequest } from '$fluidkit/auth';")

    if custom_types:
        by_namespace: dict[str, list[str]] = {}
        for type_name, module in custom_types.items():
            ns = module_to_namespace(module)
            by_namespace.setdefault(ns, []).append(type_name)

        w.line(f"import type {{ {', '.join(sorted(by_namespace.keys()))} }} from '$fluidkit/schema';")
        w.blank()
        for ns, type_names in sorted(by_namespace.items()):
            for type_name in sorted(type_names):
                w.line(f"type {type_name} = {ns}.{type_name};")


def _ts_params(parameters: list[ParameterMetadata]) -> str:
    return ", ".join(f"{p.name}{'?' if not p.required else ''}: {annotation_to_ts(p.annotation)}" for p in parameters)


def _ts_body(parameters: list[ParameterMetadata]) -> str:
    if not parameters:
        return "JSON.stringify({})"
    return f"JSON.stringify({{ {', '.join(p.name for p in parameters)} }})"


# ── Shared helpers ────────────────────────────────────────────────────────


def _build_signature(fn: FunctionMetadata, kind: str, *, param_style: str = "typed") -> str:
    if not fn.parameters:
        return f"export const {fn.name} = {kind}(async () => {{"

    unchecked = "'unchecked', "

    if param_style == "data":
        return f"export const {fn.name} = {kind}({unchecked}async (data) => {{"

    if param_style == "flat" or len(fn.parameters) == 1:
        return f"export const {fn.name} = {kind}({unchecked}async ({_ts_params(fn.parameters)}) => {{"

    destructuring = ", ".join(p.name for p in fn.parameters)
    return (
        f"export const {fn.name} = {kind}({unchecked}async ({{{destructuring}}}: {{{_ts_params(fn.parameters)}}}) => {{"
    )


def _render_fetch(w: TSWriter, route: str, params: list[ParameterMetadata]) -> None:
    with w.block(f"const _fk_res = await fetch(`${{BASE_URL}}{route}`, {{", "});"):
        w.line("method: 'POST',")
        with w.block("headers: {", "},"):
            w.line("'Content-Type': 'application/json',")
            w.line("'Cookie': _fk_cookies.getAll().map(c => `${c.name}=${c.value}`).join('; '),")
            w.line("'X-FluidKit-Token': signRequest(),")
        w.line(f"body: {_ts_body(params)},")


def _render_form_fetch(w: TSWriter, route: str) -> None:
    w.line("let _fk_res: Response;")
    w.line("if (!hasFiles(data)) {")
    w.indent()
    with w.block(f"_fk_res = await fetch(`${{BASE_URL}}{route}`, {{", "});"):
        w.line("method: 'POST',")
        with w.block("headers: {", "},"):
            w.line("'Content-Type': 'application/json',")
            w.line("'Cookie': _fk_cookies.getAll().map(c => `${c.name}=${c.value}`).join('; '),")
            w.line("'X-FluidKit-Token': signRequest(),")
        w.line("body: JSON.stringify(data),")
    w.dedent()
    w.line("} else {")
    w.indent()
    w.line("const { json: _fk_json, files: _fk_files } = extractFiles(data);")
    w.line("const _fk_form = new FormData();")
    w.line("_fk_form.append('__fluidkit_data', JSON.stringify(_fk_json));")
    with w.block("for (const [_fk_path, _fk_file] of _fk_files) {", "}"):
        w.line("_fk_form.append(_fk_path, _fk_file);")
    with w.block(f"_fk_res = await fetch(`${{BASE_URL}}{route}`, {{", "});"):
        w.line("method: 'POST',")
        with w.block("headers: {", "},"):
            w.line("'Cookie': _fk_cookies.getAll().map(c => `${c.name}=${c.value}`).join('; '),")
        w.line("body: _fk_form,")
    w.dedent()
    w.line("}")


def _render_error_block(w: TSWriter) -> None:
    with w.block("if (!_fk_res.ok) {", "}"):
        w.line("const _fk_err = await _fk_res.json();")
        w.line("if (_fk_err.__fluidkit_error) console.error(_fk_err.__fluidkit_error.traceback);")
        w.line("error(_fk_res.status, _fk_err.message ?? 'Unexpected error');")


def _render_cookie_forward_block(w: TSWriter) -> None:
    with w.block("for (const { name: _fk_cn, value: _fk_cv, ..._fk_co } of _fk_body.__fluidkit?.cookies ?? []) {", "}"):
        w.line("_fk_cookies.set(_fk_cn, _fk_cv, _fk_co);")


def _render_mutations_block(w: TSWriter) -> None:
    with w.block(
        "for (const { key: _fk_key, args: _fk_args, data: _fk_data } of _fk_body.__fluidkit?.mutations ?? []) {", "}"
    ):
        w.line("const _fk_fn = getRemoteFunction(_fk_key);")
        w.line("if (_fk_fn) _fk_fn(_fk_args, _fk_data);")


# ── Renderers ────────────────────────────────────────────────────────


def _render_query(w: TSWriter, fn: FunctionMetadata) -> None:
    route = generate_route_path(fn)
    return_type = annotation_to_ts(fn.return_annotation)
    with w.block(_build_signature(fn, "query"), "});"):
        w.line("const { cookies: _fk_cookies } = getRequestEvent();")
        _render_fetch(w, route, fn.parameters)
        _render_error_block(w)
        w.line("const _fk_body = await _fk_res.json();")
        w.line(f"return _fk_body.result as {return_type};")


def _render_query_batch(w: TSWriter, fn: FunctionMetadata) -> None:
    route = generate_route_path(fn)

    if not fn.parameters:
        logger.warning("@query.batch '%s' has no parameters — batch requires a list parameter", fn.name)
        return

    param = fn.parameters[0]
    inner_type = "any"
    if param.annotation.container == ContainerType.ARRAY and param.annotation.args:
        inner_type = annotation_to_ts(param.annotation.args[0])

    with w.block(
        f"export const {fn.name} = query.batch('unchecked', async ({param.name}: {inner_type}[]) => {{", "});"
    ):
        w.line("const { cookies: _fk_cookies } = getRequestEvent();")
        with w.block(f"const _fk_res = await fetch(`${{BASE_URL}}{route}`, {{", "});"):
            w.line("method: 'POST',")
            with w.block("headers: {", "},"):
                w.line("'Content-Type': 'application/json',")
                w.line("'Cookie': _fk_cookies.getAll().map(c => `${c.name}=${c.value}`).join('; '),")
                w.line("'X-FluidKit-Token': signRequest(),")
            w.line(f"body: JSON.stringify({{ args: {param.name} }}),")
        _render_error_block(w)
        w.line("const _fk_body = await _fk_res.json();")
        w.line(f"return (_fk_input: {inner_type}, _fk_idx: number) => _fk_body.results[_fk_idx];")


def _render_command(w: TSWriter, fn: FunctionMetadata) -> None:
    route = generate_route_path(fn)
    return_type = annotation_to_ts(fn.return_annotation)
    with w.block(_build_signature(fn, "command"), "});"):
        w.line("const { cookies: _fk_cookies } = getRequestEvent();")
        _render_fetch(w, route, fn.parameters)
        _render_error_block(w)
        w.line("const _fk_body = await _fk_res.json();")
        _render_cookie_forward_block(w)
        _render_mutations_block(w)
        w.line(f"return _fk_body.result as {return_type};")


def _render_form(w: TSWriter, fn: FunctionMetadata) -> None:
    return_type = annotation_to_ts(fn.return_annotation)
    with w.block(_build_signature(fn, "form", param_style="data"), "});"):
        w.line("const { cookies: _fk_cookies } = getRequestEvent();")
        w.blank()
        _render_form_fetch(w, generate_route_path(fn))
        w.blank()
        _render_error_block(w)
        w.line("const _fk_body = await _fk_res.json();")
        _render_cookie_forward_block(w)
        w.line("if ('redirect' in _fk_body) redirect(_fk_body.redirect.status, _fk_body.redirect.location);")
        _render_mutations_block(w)
        w.line(f"return _fk_body.result as {return_type};")


def _render_prerender(w: TSWriter, fn: FunctionMetadata) -> None:
    route = generate_route_path(fn)
    return_type = annotation_to_ts(fn.return_annotation)
    signature = _build_signature(fn, "prerender", param_style="flat")

    has_options = fn.prerender_dynamic or fn.prerender_inputs is not None

    def _body():
        w.line("const { cookies: _fk_cookies } = getRequestEvent();")
        _render_fetch(w, route, fn.parameters)
        _render_error_block(w)
        w.line("const _fk_body = await _fk_res.json();")
        w.line(f"return _fk_body.result as {return_type};")

    if has_options:
        w.line(signature)
        w.indent()
        _body()
        w.dedent()
        with w.block("}, {", "});"):
            if fn.prerender_inputs is not None and not callable(fn.prerender_inputs):
                w.line(f"inputs: () => {json.dumps(fn.prerender_inputs)},")
            if fn.prerender_dynamic:
                w.line("dynamic: true,")
    else:
        with w.block(signature, "});"):
            _body()


def _render_registration(w: TSWriter, fn: FunctionMetadata) -> None:
    key = f"{fn.module}#{fn.name}"
    if not fn.parameters:
        call = f"{fn.name}().set(_fk_data);"
    elif fn.decorator_type == DecoratorType.QUERY_BATCH:
        call = f"{fn.name}((Object.values(_fk_args) as any[])[0]).set(_fk_data);"
    else:
        call = f"{fn.name}(_fk_args).set(_fk_data);"
    with w.block(f"registerRemoteFunction('{key}', (_fk_args: any, _fk_data: any) => {{", "});"):
        w.line(call)
