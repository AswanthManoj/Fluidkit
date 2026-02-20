import re
from pathlib import Path


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
