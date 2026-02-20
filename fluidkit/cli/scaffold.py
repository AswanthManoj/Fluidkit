import sys
import typer
import shutil
from pathlib import Path
from .utils import get_npx, get_npm, _fmt
from .config import write_default_config, load_config
from .patch import patch_svelte_config, patch_vite_config


def copy_runtime_files(schema_output: str = "src/lib/fluidkit") -> None:
    runtime_src = Path(__file__).parent.parent / "runtime"
    dest = Path(schema_output)
    dest.mkdir(parents=True, exist_ok=True)
    for file in ("registry.ts", "types.ts"):
        src = runtime_src / file
        if src.exists():
            shutil.copy2(src, dest / file)


def scaffold_project():
    npx = get_npx()
    npm = get_npm()

    result = npx(
        ["sv", "create", ".", "--no-dir-check", "--no-install", "--template", "minimal"],
        return_completed_process=True
    )
    if result.returncode != 0:
        typer.echo(_fmt("fluidkit", "sv create failed."))
        sys.exit(result.returncode)

    typer.echo(_fmt("fluidkit", "installing dependencies..."))
    result = npm(["install"], return_completed_process=True)
    if result.returncode != 0:
        typer.echo(_fmt("fluidkit", "npm install failed."))
        sys.exit(result.returncode)

    # Write config first — everything else derives from it
    write_default_config()
    config = load_config()

    # Copy runtime files into schema_output
    copy_runtime_files(schema_output=config["schema_output"])
    typer.echo(_fmt("fluidkit", f"runtime files copied to {config['schema_output']}"))

    # Patch svelte.config
    ok = patch_svelte_config(schema_output=config["schema_output"])
    if ok:
        typer.echo(_fmt("fluidkit", "patched svelte.config"))
    else:
        typer.echo(_fmt("fluidkit", "⚠ could not patch svelte.config — add this manually:"))
        typer.echo(f"    kit: {{ alias: {{ '$fluidkit': './{config['schema_output']}' }} }}")

    # Patch vite.config
    ok = patch_vite_config(frontend_port=config["frontend_port"])
    if ok:
        typer.echo(_fmt("fluidkit", "patched vite.config"))
    else:
        typer.echo(_fmt("fluidkit", "⚠ could not patch vite.config — add this manually:"))
        typer.echo(f"    server: {{ port: {config['frontend_port']} }}")

    typer.echo(_fmt("fluidkit", "done! run: fluidkit dev src/main.py"))
