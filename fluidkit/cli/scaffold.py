import sys
import typer
import shutil
from pathlib import Path
from .utils import get_npx, get_npm, _fmt
from .config import write_default_config, load_config
from .patch import patch_svelte_config, patch_vite_config, patch_svelte_experimental


def copy_runtime_files(schema_output: str = "src/lib/fluidkit") -> None:
    runtime_src = Path(__file__).parent.parent / "runtime"
    dest = Path(schema_output)
    dest.mkdir(parents=True, exist_ok=True)
    for file in ("registry.ts", "types.ts"):
        src = runtime_src / file
        if src.exists():
            shutil.copy2(src, dest / file)


def copy_template_files() -> None:
    templates_src = Path(__file__).parent.parent / "runtime" / "templates"

    for init_path in ("src/__init__.py", "src/lib/__init__.py"):
        p = Path(init_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
    
    mapping = {
        "app.py":       "src/app.py",
        "demo.py":      "src/lib/demo.py",
        "+page.svelte": "src/routes/+page.svelte",
        "+layout.svelte": "src/routes/+layout.svelte",
        "demo.remote.ts": "src/lib/demo.remote.ts",
        "IntroComponent.svelte": "src/lib/components/IntroComponent.svelte",
    }
    for src_name, dest_path in mapping.items():
        src = templates_src / src_name
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.copy2(src, dest)


def write_gitignore(project_root: str = ".") -> None:
    gitignore_path = Path(project_root) / ".gitignore"
    content = Path(__file__).parent.parent / "runtime" / ".gitignore.template"
    gitignore_path.write_text(content.read_text(encoding="utf-8"), encoding="utf-8")


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

    write_default_config()
    write_gitignore()
    config = load_config()

    copy_runtime_files(schema_output=config["schema_output"])
    typer.echo(_fmt("fluidkit", f"runtime files copied to {config['schema_output']}"))

    copy_template_files()
    typer.echo(_fmt("fluidkit", "scaffolded src/"))

    ok = patch_svelte_config(schema_output=config["schema_output"])
    if ok:
        typer.echo(_fmt("fluidkit", "patched svelte.config"))
    else:
        typer.echo(_fmt("fluidkit", "⚠ could not patch svelte.config — add this manually:"))
        typer.echo(f"    kit: {{ alias: {{ '$fluidkit': './{config['schema_output']}' }} }}")

    ok = patch_svelte_experimental()
    if ok:
        typer.echo(_fmt("fluidkit", "set experimental flags in svelte.config"))
    else:
        typer.echo(_fmt("fluidkit", "⚠ could not set experimental flags — add them manually:"))
        typer.echo("    kit: { experimental: { remoteFunctions: true } }")
        typer.echo("    compilerOptions: { experimental: { async: true } }")

    ok = patch_vite_config(frontend_port=config["frontend_port"])
    if ok:
        typer.echo(_fmt("fluidkit", "patched vite.config"))
    else:
        typer.echo(_fmt("fluidkit", "⚠ could not patch vite.config — add this manually:"))
        typer.echo(f"    server: {{ port: {config['frontend_port']} }}")

    typer.echo(_fmt("fluidkit", f"done! run: `fluidkit dev`"))
