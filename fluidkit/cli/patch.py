import re
import json
from pathlib import Path


_EXPERIMENTAL_MERGE = {
    "kit": {
        "experimental": {
            "remoteFunctions": True
        }
    },
    "compilerOptions": {
        "experimental": {
            "async": True
        }
    }
}


_PATCH_SCRIPT = """\
import fs from "fs";
import {{ parse }} from "acorn";
import {{ print }} from "esrap";
import ts from "esrap/languages/ts";

const MERGE = {merge};
const src = fs.readFileSync({config_path}, "utf8");
const ast = parse(src, {{ ecmaVersion: "latest", sourceType: "module" }});

let configObj = null;
const body = ast.body;
const defaultExport = body.find(n => n.type === "ExportDefaultDeclaration");

if (defaultExport?.declaration?.type === "ObjectExpression") {{
  configObj = defaultExport.declaration;
}} else if (defaultExport?.declaration?.type === "Identifier") {{
  const name = defaultExport.declaration.name;
  for (const node of body) {{
    if (node.type !== "VariableDeclaration") continue;
    for (const d of node.declarations) {{
      if (d.id?.name === name && d.init?.type === "ObjectExpression") configObj = d.init;
    }}
  }}
}}

if (!configObj) throw new Error("Could not find config ObjectExpression");

function toAst(val) {{
  if (typeof val === "boolean") return {{ type: "Literal", value: val, raw: String(val) }};
  if (typeof val === "string")  return {{ type: "Literal", value: val, raw: JSON.stringify(val) }};
  if (typeof val === "number")  return {{ type: "Literal", value: val, raw: String(val) }};
  if (val && typeof val === "object") {{
    return {{
      type: "ObjectExpression",
      properties: Object.entries(val).map(([k, v]) => ({{
        type: "Property", kind: "init", computed: false,
        shorthand: false, method: false,
        key: {{ type: "Identifier", name: k }},
        value: toAst(v)
      }}))
    }};
  }}
  throw new Error("Unsupported type: " + typeof val);
}}

function findProp(objExpr, key) {{
  return objExpr.properties.find(p => (p.key?.name ?? p.key?.value) === key);
}}

function mergeInto(objExpr, data) {{
  for (const [key, value] of Object.entries(data)) {{
    const existing = findProp(objExpr, key);
    if (existing && typeof value === "object" && existing.value?.type === "ObjectExpression") {{
      mergeInto(existing.value, value);
    }} else if (existing) {{
      existing.value = toAst(value);
    }} else {{
      objExpr.properties.push({{
        type: "Property", kind: "init", computed: false,
        shorthand: false, method: false,
        key: {{ type: "Identifier", name: key }},
        value: toAst(value)
      }});
    }}
  }}
}}

mergeInto(configObj, MERGE);
const {{ code }} = print(ast, ts());
fs.writeFileSync({config_path}, code, "utf8");
console.log(JSON.stringify({{ok: true}}));
"""


def _extract_adapter_comments(src: str) -> list[str] | None:
    lines = src.splitlines()
    for i, line in enumerate(lines):
        if re.match(r'\s*adapter\s*:', line):
            block = []
            j = i - 1
            while j >= 0 and lines[j].strip().startswith("//"):
                block.insert(0, lines[j])
                j -= 1
            return block if block else None
    return None


def _extract_type_comment(src: str) -> str | None:
    match = re.search(r'(/\*\*[^*]*\*+(?:[^/*][^*]*\*+)*/\s*\n)(?=\s*(?:const|let|var|export\s+default)\s)', src)
    return match.group(1) if match else None


def _reinsert_adapter_comments(src: str, block: list[str]) -> str:
    lines = src.splitlines()
    for i, line in enumerate(lines):
        if re.match(r'\s*adapter\s*:', line):
            indent = line[: len(line) - len(line.lstrip())]
            indented = [indent + l.strip() for l in block]
            lines = lines[:i] + indented + lines[i:]
            break
    return "\n".join(lines) + "\n"


def _reinsert_type_comment(src: str, comment: str) -> str:
    src = re.sub(r'\s*/\*\*[^*]*\*+(?:[^/*][^*]*\*+)*/\s*', '', src)
    return re.sub(
        r'\n+(?=(?:const|let|var|export\s+default)\s)',
        '\n\n' + comment,
        src,
        count=1
    )


def patch_svelte_experimental(project_root: str = ".") -> bool:
    try:
        from nodejs_wheel import node
    except ImportError:
        return False

    for name in ("svelte.config.js", "svelte.config.ts"):
        config_path = Path(project_root) / name
        if config_path.exists():
            break
    else:
        return False

    original_src = config_path.read_text(encoding="utf-8")
    adapter_comments = _extract_adapter_comments(original_src)
    type_comment = _extract_type_comment(original_src)

    script = _PATCH_SCRIPT.format(
        config_path=json.dumps(str(config_path.resolve()).replace("\\", "/")),
        merge=json.dumps(_EXPERIMENTAL_MERGE, indent=2)
    )

    tmp = Path(project_root) / "_fluidkit_patch.mjs"
    try:
        tmp.write_text(script, encoding="utf-8")
        result = node(
            [str(tmp)],
            cwd=str(Path(project_root).resolve()),
            return_completed_process=True,
            capture_output=True,
        )
        if result.returncode != 0:
            stderr = (result.stderr or b"").decode(errors="replace").strip()
            if stderr:
                import typer
                typer.echo(
                    typer.style("  [fluid]", fg=typer.colors.BRIGHT_YELLOW, bold=True)
                    + f" experimental patch failed: {stderr}"
                )
            return False

        patched_src = config_path.read_text(encoding="utf-8")
        if adapter_comments:
            patched_src = _reinsert_adapter_comments(patched_src, adapter_comments)
            config_path.write_text(patched_src, encoding="utf-8")

        if type_comment:
            patched_src = _reinsert_type_comment(patched_src, type_comment)
            config_path.write_text(patched_src, encoding="utf-8")

        return json.loads(result.stdout).get("ok", False)
    except (json.JSONDecodeError, AttributeError, OSError):
        return False
    finally:
        tmp.unlink(missing_ok=True)


def check_svelte_experimental(project_root: str = ".") -> None:
    for name in ("svelte.config.js", "svelte.config.ts"):
        config_path = Path(project_root) / name
        if config_path.exists():
            break
    else:
        return

    original = config_path.read_text(encoding="utf-8")
    missing = []
    if "remoteFunctions" not in original:
        missing.append("kit.experimental.remoteFunctions: true")
    if re.search(r'compilerOptions', original) is None or "async" not in original:
        missing.append("compilerOptions.experimental.async: true")

    if missing:
        import typer
        typer.echo(
            typer.style("  [fluid]", fg=typer.colors.BRIGHT_YELLOW, bold=True)
            + " svelte.config missing: " + ", ".join(missing)
        )


def patch_svelte_config(project_root: str = ".", schema_output: str = "src/lib/fluidkit") -> bool:
    alias_value = f"'$fluidkit': './{schema_output}'"

    for name in ("svelte.config.js", "svelte.config.ts"):
        config_path = Path(project_root) / name
        if config_path.exists():
            break
    else:
        return False

    original = config_path.read_text(encoding="utf-8")

    # Case 1: $fluidkit alias already exists — check if stale
    existing = re.search(r"""['"]?\$fluidkit['"]?\s*:\s*['"]([^'"]+)['"]""", original)
    if existing:
        if existing.group(1) == f"./{schema_output}":
            return True
        patched = original[:existing.start(1)] + f"./{schema_output}" + original[existing.end(1):]
        config_path.write_text(patched, encoding="utf-8")
        return True

    # Case 2: alias block exists, inject inside it
    alias_block = re.search(r'alias\s*:\s*\{', original)
    if alias_block:
        insert_at = alias_block.end()
        patched = original[:insert_at] + f"\n      {alias_value}," + original[insert_at:]
        config_path.write_text(patched, encoding="utf-8")
        return True

    # Case 3: adapter() exists — inject after it, ensuring trailing comma on adapter line
    adapter_match = re.search(r'(adapter\([^)]*\))', original)
    if adapter_match:
        insert_at = adapter_match.end()
        after = original[insert_at:]
        has_comma = bool(re.match(r'\s*,', after))
        comma = '' if has_comma else ','
        patched = (
            original[:insert_at]
            + comma
            + f"\n\t\talias: {{\n\t\t\t{alias_value}\n\t\t}},"
            + original[insert_at:]
        )
        config_path.write_text(patched, encoding="utf-8")
        return True

    # Case 4: inject after kit: {
    kit_match = re.search(r'kit\s*:\s*\{', original)
    if kit_match:
        insert_at = kit_match.end()
        patched = (
            original[:insert_at]
            + f"\n\t\talias: {{\n\t\t\t{alias_value}\n\t\t}},"
            + original[insert_at:]
        )
        config_path.write_text(patched, encoding="utf-8")
        return True

    return False


def patch_vite_config(project_root: str = ".", frontend_port: int = 5173) -> bool:
    for name in ("vite.config.ts", "vite.config.js"):
        config_path = Path(project_root) / name
        if config_path.exists():
            break
    else:
        return False

    original = config_path.read_text(encoding="utf-8")

    # Case 1: port already exists — check if stale
    existing = re.search(r'port\s*:\s*(\d+)', original)
    if existing:
        if int(existing.group(1)) == frontend_port:
            return True
        patched = original[:existing.start(1)] + str(frontend_port) + original[existing.end(1):]
        config_path.write_text(patched, encoding="utf-8")
        return True

    # Case 2: server block exists but no port — inject inside
    server_match = re.search(r'server\s*:\s*\{', original)
    if server_match:
        insert_at = server_match.end()
        patched = original[:insert_at] + f"\n\t\tport: {frontend_port}," + original[insert_at:]
        config_path.write_text(patched, encoding="utf-8")
        return True

    # Case 3: no server block — inject before closing } of defineConfig
    define_close = re.search(r'(\})\s*\)\s*;?\s*$', original, re.DOTALL)
    if define_close:
        insert_at = define_close.start(1)
        before = original[:insert_at].rstrip()
        comma = ',' if before and before[-1] not in (',', '{') else ''
        patched = (
            before
            + comma
            + f"\n\tserver: {{\n\t\tport: {frontend_port}\n\t}}\n"
            + original[insert_at:]
        )
        config_path.write_text(patched, encoding="utf-8")
        return True

    return False
