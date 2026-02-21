import re
import sys
import typer
import asyncio
import logging
import threading
import importlib.util
from pathlib import Path
from fluidkit import __version__
from fluidkit.registry import fluidkit_registry


class _FluidKitLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        msg = self.format(record)
        if re.search(r'" 2\d{2}', msg):
            return
        if record.levelno >= logging.ERROR:
            color = typer.colors.BRIGHT_RED
        elif record.levelno >= logging.WARNING:
            color = typer.colors.BRIGHT_YELLOW
        else:
            color = typer.colors.BRIGHT_CYAN
        typer.echo(typer.style("  [fluid]", fg=color, bold=True) + f" {msg}")


def _setup_logging():
    fmt = logging.Formatter("%(message)s")
    handler = _FluidKitLogHandler()
    handler.setFormatter(fmt)
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "jurigged"):
        log = logging.getLogger(name)
        log.handlers = [handler]
        log.propagate = False
        if log.level == logging.NOTSET:
            log.setLevel(logging.DEBUG)


def load_entry(entry: str) -> None:
    path = Path(entry).resolve()
    if not path.exists():
        typer.echo(typer.style("  [fluid]", fg=typer.colors.BRIGHT_CYAN, bold=True) + f" entry not found: {entry}")
        raise SystemExit(1)

    cwd = Path.cwd()
    # Derive "src.app" from "src/app.py"
    module_name = ".".join(path.relative_to(cwd).with_suffix("").parts)

    if str(cwd) not in sys.path:
        sys.path.insert(0, str(cwd))

    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    sys.modules["__main__"] = module
    spec.loader.exec_module(module)


async def _stream(stream, prefix: str, color):
    async for line in stream:
        text = line.decode(errors="replace").rstrip()
        if text:
            typer.echo(typer.style(f"  [{prefix}]", fg=color, bold=True) + f" {text}")


async def _dev_main(config: dict) -> None:
    import uvicorn
    import jurigged
    from fluidkit import hmr
    from fluidkit.codegen import generate, watch as codegen_watch

    load_entry(config["entry"])

    fluidkit_registry.dev = True

    base_url = f"http://{'localhost' if config['host'] == '0.0.0.0' else config['host']}:{config['backend_port']}"
    generate(fluidkit_registry.functions, base_url=base_url, schema_output=config["schema_output"])
    codegen_watch(fluidkit_registry, base_url=base_url, schema_output=config["schema_output"])
    
    def _jurigged_logger(op):
        if str(op).startswith("Watch"):
            return
        if str(op).startswith("Update"):
            typer.echo(
                typer.style("  [fluid] ", fg=typer.colors.BRIGHT_CYAN, bold=True)
                + typer.style("(server) ", fg=typer.colors.Blu)
                + typer.style("hmr update", fg=typer.colors.BRIGHT_GREEN)
                + f" {op}"
            )
        else:
            typer.echo(
                typer.style("  [fluid] ", fg=typer.colors.BRIGHT_CYAN, bold=True) 
                + typer.style("(server) ", fg=typer.colors.BLUE)
                + f" {op}"
            )

    watcher = jurigged.watch(
        logger=_jurigged_logger,
        pattern=config["watch_pattern"]
    )
    hmr.setup(watcher)
    for metadata in fluidkit_registry.functions.values():
        hmr.attach_conform(metadata)

    _setup_logging()
    server = uvicorn.Server(uvicorn.Config(
        fluidkit_registry.app,
        host=config["host"],
        port=config["backend_port"],
        log_config=None,
    ))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    proc = await asyncio.create_subprocess_exec(
        "npm", "run", "dev",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        await asyncio.gather(
            _stream(proc.stdout, "vite", typer.colors.BRIGHT_GREEN),
            _stream(proc.stderr, "vite", typer.colors.BRIGHT_YELLOW),
        )
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        proc.terminate()
        await proc.wait()
        server.should_exit = True
        thread.join(timeout=5)


def run_dev(config: dict) -> None:
    display_host = "localhost" if config["host"] == "0.0.0.0" else config["host"]
    typer.echo(typer.style(f"\n  fluidkit v{__version__}\n", fg=typer.colors.BRIGHT_CYAN, bold=True))
    typer.echo("  → " + typer.style("[fluid]", fg=typer.colors.BRIGHT_CYAN, bold=True) + f"  http://{display_host}:{config['backend_port']}")
    typer.echo("  → " + typer.style("[vite] ", fg=typer.colors.BRIGHT_GREEN,  bold=True) + f"  http://localhost:{config['frontend_port']}\n")
    try:
        asyncio.run(_dev_main(config))
    except KeyboardInterrupt:
        pass


def run_build(config: dict) -> None:
    import subprocess
    from fluidkit.codegen import generate

    load_entry(config["entry"])

    base_url = f"http://localhost:{config['backend_port']}"
    generate(
        functions=fluidkit_registry.functions,
        base_url=base_url,
        schema_output=config["schema_output"],
    )
    typer.echo(typer.style("  [fluid]", fg=typer.colors.BRIGHT_CYAN, bold=True) + " codegen done")

    result = subprocess.run(["npm", "run", "build"])
    if result.returncode != 0:
        raise SystemExit(result.returncode)
