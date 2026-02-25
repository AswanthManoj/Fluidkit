import sys
import asyncio
import threading
import importlib.util
from pathlib import Path
from fluidkit import __version__
from fluidkit.registry import fluidkit_registry
from .utils import setup_logging, header, hmr_update, echo, display_host, _COLORS


def load_entry(entry: str) -> None:
    path = Path(entry).resolve()
    if not path.exists():
        echo("fluid", f"entry not found: {entry}", _COLORS["error"])
        raise SystemExit(1)

    cwd = Path.cwd()
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
            echo(prefix, text, color)


async def _run_servers(config: dict, npm_command: str, hmr: bool = True) -> None:
    import uvicorn
    from fluidkit.codegen import generate, watch as codegen_watch

    load_entry(config["entry"])
    fluidkit_registry.dev = True

    base_url = f"http://{display_host(config)}:{config['backend_port']}"
    generate(fluidkit_registry.functions, base_url=base_url, schema_output=config["schema_output"])
    codegen_watch(fluidkit_registry, base_url=base_url, schema_output=config["schema_output"])

    if hmr:
        import jurigged
        from fluidkit import hmr as hmr_module

        watcher = jurigged.watch(
            logger=hmr_update,
            pattern=config["watch_pattern"]
        )
        watch_dir = str(Path(config["entry"]).parent)
        hmr_module.setup(watcher, watch_paths=(watch_dir,))

        for metadata in fluidkit_registry.functions.values():
            hmr_module.attach_conform(metadata)
        echo("fluid", "HMR enabled", _COLORS["warn"])
    else:
        echo("fluid", "HMR disabled", _COLORS["warn"])

    setup_logging()

    server = uvicorn.Server(uvicorn.Config(
        fluidkit_registry.app,
        host=config["host"],
        port=config["backend_port"],
        log_config=None,
        reload=not hmr,
    ))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    proc = await asyncio.create_subprocess_exec(
        "npm", "run", npm_command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        await asyncio.gather(
            _stream(proc.stdout, "vite", _COLORS["vite"]),
            _stream(proc.stderr, "vite", _COLORS["warn"]),
        )
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        proc.terminate()
        await proc.wait()
        server.should_exit = True
        thread.join(timeout=5)


def _run_with_header(config: dict, npm_command: str, hmr: bool = False) -> None:
    host = display_host(config)
    header(
        version=__version__,
        fluid_url=f"http://{host}:{config['backend_port']}",
        vite_url=f"http://localhost:{config['frontend_port']}"
    )
    try:
        asyncio.run(_run_servers(config, npm_command=npm_command, hmr=hmr))
    except KeyboardInterrupt:
        pass


def run_dev(config: dict, hmr: bool = True) -> None:
    _run_with_header(config, "dev", hmr=hmr)


def run_preview(config: dict) -> None:
    _run_with_header(config, "preview", hmr=False)


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
    echo("fluid", "codegen done")

    result = subprocess.run(["npm", "run", "build"])
    if result.returncode != 0:
        raise SystemExit(result.returncode)
