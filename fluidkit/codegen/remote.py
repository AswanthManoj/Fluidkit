import logging
from pathlib import Path
from typing import Dict, List, Set
from fluidkit.utilities import generate_route_path
from fluidkit.codegen.ts import GENERATED_FILE_WARNING, TSWriter, annotation_to_ts, module_to_namespace
from fluidkit.models import FunctionMetadata, DecoratorType, ParameterMetadata, FieldAnnotation, BaseType, ContainerType


logger = logging.getLogger(__name__)


def generate_remote_files(
    functions: Dict[str, FunctionMetadata],
    base_url: str = "http://localhost:8000",
) -> None:
    by_file: Dict[str, List[FunctionMetadata]] = {}
    for fn in functions.values():
        if fn.file_path:
            by_file.setdefault(fn.file_path, []).append(fn)

    for file_path, fns in by_file.items():
        content = render_remote_file(fns, base_url)
        if not content:
            continue
        out_path = file_path.replace(".py", ".remote.ts")
        Path(out_path).write_text(content, encoding="utf-8")
        logger.debug("generated %s", out_path)


def render_remote_file(functions: List[FunctionMetadata], base_url: str) -> str:
    functions = [f for f in functions if f.decorator_type != DecoratorType.PRERENDER]
    if not functions:
        return ""

    types = {f.decorator_type for f in functions}
    has_mutations = bool(types & {DecoratorType.COMMAND, DecoratorType.FORM})
    has_registrations = bool(types & {DecoratorType.QUERY, DecoratorType.PRERENDER})
    custom_types = _collect_custom_types(functions)

    w = TSWriter()
    w.line(GENERATED_FILE_WARNING)
    _render_imports(w, types, has_mutations, has_registrations, custom_types)
    w.blank()
    w.line(f'const BASE_URL = "{base_url}";')

    for fn in functions:
        w.blank()
        if fn.decorator_type == DecoratorType.QUERY:
            _render_query(w, fn)
        elif fn.decorator_type == DecoratorType.PRERENDER:
            _render_prerender(w, fn)
        elif fn.decorator_type == DecoratorType.FORM:
            _render_form(w, fn)
        elif fn.decorator_type == DecoratorType.COMMAND:
            _render_command(w, fn)

    if has_registrations:
        w.blank()
        for fn in functions:
            if fn.decorator_type in (DecoratorType.QUERY, DecoratorType.PRERENDER):
                _render_registration(w, fn)

    return w.render()


def _collect_custom_types(functions: List[FunctionMetadata]) -> Dict[str, str]:
    found: Dict[str, str] = {}

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
    types: Set[DecoratorType],
    has_mutations: bool,
    has_registrations: bool,
    custom_types: Dict[str, str],
) -> None:
    has_forms = bool(types & {DecoratorType.FORM})
    kit_imports = ["error"]
    if has_forms:
        kit_imports.append("redirect")
    w.line(f"import {{ {', '.join(kit_imports)} }} from '@sveltejs/kit';")

    app_imports = sorted({
        'prerender' if t == DecoratorType.PRERENDER else t.value
        for t in types
    }) + ["getRequestEvent"]
    w.line(f"import {{ {', '.join(app_imports)} }} from '$app/server';")

    registry_imports = []
    if has_mutations:
        registry_imports.append("getRemoteFunction")
    if has_registrations:
        registry_imports.append("registerRemoteFunction")
    if registry_imports:
        w.line(f"import {{ {', '.join(registry_imports)} }} from '$fluidkit/registry';")

    if custom_types:
        by_namespace: Dict[str, List[str]] = {}
        for type_name, module in custom_types.items():
            ns = module_to_namespace(module)
            by_namespace.setdefault(ns, []).append(type_name)

        w.line(f"import type {{ {', '.join(sorted(by_namespace.keys()))} }} from '$fluidkit/schema';")
        w.blank()
        for ns, type_names in sorted(by_namespace.items()):
            for type_name in sorted(type_names):
                w.line(f"type {type_name} = {ns}.{type_name};")

def _ts_params(parameters: List[ParameterMetadata]) -> str:
    return ", ".join(
        f"{p.name}{'?' if not p.required else ''}: {annotation_to_ts(p.annotation)}"
        for p in parameters
    )


def _ts_body(parameters: List[ParameterMetadata]) -> str:
    if not parameters:
        return "JSON.stringify({})"
    return f"JSON.stringify({{ {', '.join(p.name for p in parameters)} }})"


# =============================================================================
# Shared block helpers
# =============================================================================

def _render_error_block(w: TSWriter) -> None:
    with w.block("if (!_fk_res.ok) {", "}"):
        w.line("const _fk_err = await _fk_res.json();")
        w.line("if (_fk_err.__fluidkit_error) console.error(_fk_err.__fluidkit_error.traceback);")
        w.line("error(_fk_res.status, _fk_err.message ?? 'Unexpected error');")


def _render_cookie_forward_block(w: TSWriter) -> None:
    with w.block("for (const _fk_sc of _fk_res.headers.getSetCookie()) {", "}"):
        w.line("const [_fk_nv] = _fk_sc.split(';');")
        w.line("const [_fk_name, _fk_val] = _fk_nv.split('=');")
        w.line("_fk_cookies.set(_fk_name.trim(), _fk_val?.trim() ?? '', { path: '/' });")


def _render_mutations_block(w: TSWriter) -> None:
    with w.block("for (const { key: _fk_key, args: _fk_args, data: _fk_data } of _fk_body.__fluidkit?.mutations ?? []) {", "}"):
        w.line("const _fk_fn = getRemoteFunction(_fk_key);")
        w.line("if (_fk_fn) _fk_fn(_fk_args, _fk_data);")


# =============================================================================
# Renderers
# =============================================================================

def _render_query(w: TSWriter, fn: FunctionMetadata) -> None:
    route = generate_route_path(fn)
    return_type = annotation_to_ts(fn.return_annotation)
    if fn.parameters:
        if len(fn.parameters) == 1:
            signature = f"export const {fn.name} = query('unchecked', async ({_ts_params(fn.parameters)}) => {{"
        else:
            destructuring_pattern = ", ".join(p.name for p in fn.parameters)
            signature = f"export const {fn.name} = query('unchecked', async ({{{destructuring_pattern}}}: {{{_ts_params(fn.parameters)}}}) => {{"
    else:
        signature = f"export const {fn.name} = query(async () => {{"
    
    with w.block(signature, "});"):
        w.line("const { cookies: _fk_cookies } = getRequestEvent();")
        with w.block(f"const _fk_res = await fetch(`${{BASE_URL}}{route}`, {{", "});"):
            w.line("method: 'POST',")
            with w.block("headers: {", "},"):
                w.line("'Content-Type': 'application/json',")
                w.line("'Cookie': _fk_cookies.getAll().map(c => `${c.name}=${c.value}`).join('; '),")
            w.line(f"body: {_ts_body(fn.parameters)},")
        _render_error_block(w)
        w.line("const _fk_body = await _fk_res.json();")
        w.line(f"return _fk_body.result as {return_type};")


def _render_prerender(w: TSWriter, fn: FunctionMetadata) -> None:
    route = generate_route_path(fn)
    return_type = annotation_to_ts(fn.return_annotation)
    signature = (
        f"export const {fn.name} = prerender('unchecked', async ({_ts_params(fn.parameters)}) => {{"
        if fn.parameters
        else f"export const {fn.name} = prerender(async () => {{"
    )

    has_options = fn.prerender_dynamic or (
        fn.prerender_inputs is not None and not callable(fn.prerender_inputs)
    )

    if callable(fn.prerender_inputs):
        logger.warning(
            "@prerender '%s' has callable inputs — cannot serialize to codegen, skipping inputs option",
            fn.name
        )

    def _body():
        w.line("const { cookies: _fk_cookies } = getRequestEvent();")
        with w.block(f"const _fk_res = await fetch(`${{BASE_URL}}{route}`, {{", "});"):
            w.line("method: 'POST',")
            with w.block("headers: {", "},"):
                w.line("'Content-Type': 'application/json',")
                w.line("'Cookie': _fk_cookies.getAll().map(c => `${c.name}=${c.value}`).join('; '),")
            w.line(f"body: {_ts_body(fn.parameters)},")
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
                import json
                w.line(f"inputs: () => {json.dumps(fn.prerender_inputs)},")
            if fn.prerender_dynamic:
                w.line("dynamic: true,")
    else:
        with w.block(signature, "});"):
            _body()


def _render_command(w: TSWriter, fn: FunctionMetadata) -> None:
    route = generate_route_path(fn)
    return_type = annotation_to_ts(fn.return_annotation)

    if fn.parameters:
        if len(fn.parameters) == 1:
            signature = f"export const {fn.name} = command('unchecked', async ({_ts_params(fn.parameters)}) => {{"
        else:
            destructuring_pattern = ", ".join(p.name for p in fn.parameters)
            signature = f"export const {fn.name} = command('unchecked', async ({{{destructuring_pattern}}}: {{{_ts_params(fn.parameters)}}}) => {{"
    else:
        signature = f"export const {fn.name} = command(async () => {{"

    with w.block(signature, "});"):
        w.line("const { cookies: _fk_cookies } = getRequestEvent();")
        with w.block(f"const _fk_res = await fetch(`${{BASE_URL}}{route}`, {{", "});"):
            w.line("method: 'POST',")
            with w.block("headers: {", "},"):
                w.line("'Content-Type': 'application/json',")
                w.line("'Cookie': _fk_cookies.getAll().map(c => `${c.name}=${c.value}`).join('; '),")
            w.line(f"body: {_ts_body(fn.parameters)},")
        _render_cookie_forward_block(w)
        _render_error_block(w)
        w.line("const _fk_body = await _fk_res.json();")
        _render_mutations_block(w)
        w.line(f"return _fk_body.result as {return_type};")


def _render_form(w: TSWriter, fn: FunctionMetadata) -> None:
    route = generate_route_path(fn)
    return_type = annotation_to_ts(fn.return_annotation)

    if fn.parameters:
        signature = f"export const {fn.name} = form('unchecked', async (data) => {{"
    else:
        signature = f"export const {fn.name} = form(async () => {{"

    with w.block(signature, "});"):
        w.line("const { cookies: _fk_cookies } = getRequestEvent();")
        w.blank()
        w.line("const _fk_form = new FormData();")
        with w.block("for (const [key, value] of Object.entries(data)) {", "}"):
            w.line("if (Array.isArray(value)) {")
            w.indent()
            w.line("for (const v of value) _fk_form.append(key, v as string | Blob);")
            w.dedent()
            w.line("} else {")
            w.indent()
            w.line("_fk_form.append(key, value as string | Blob);")
            w.dedent()
            w.line("}")
        w.blank()
        with w.block(f"const _fk_res = await fetch(`${{BASE_URL}}{route}`, {{", "});"):
            w.line("method: 'POST',")
            with w.block("headers: {", "},"):
                w.line("'Cookie': _fk_cookies.getAll().map(c => `${c.name}=${c.value}`).join('; '),")
            w.line("body: _fk_form,")
        w.blank()
        _render_cookie_forward_block(w)
        _render_error_block(w)
        w.line("const _fk_body = await _fk_res.json();")
        w.line("if ('redirect' in _fk_body) redirect(_fk_body.redirect.status, _fk_body.redirect.location);")
        _render_mutations_block(w)
        w.line(f"return _fk_body.result as {return_type};")


def _render_registration(w: TSWriter, fn: FunctionMetadata) -> None:
    key = f"{fn.module}#{fn.name}"
    if not fn.parameters:
        call = f"{fn.name}().set(_fk_data);"
    else:
        call = f"{fn.name}(_fk_args).set(_fk_data);"

    with w.block(f"registerRemoteFunction('{key}', (_fk_args: any, _fk_data: any) => {{", "});"):
        w.line(call)

