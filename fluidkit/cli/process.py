import os
import sys
import time
import asyncio
import threading
import importlib.util
from pathlib import Path
from contextlib import contextmanager

from fluidkit import __version__
from fluidkit.registry import fluidkit_registry
from .utils import _COLORS, display_host, echo, header, hmr_update, run_node_tool, run_node_tool_async, setup_logging



def _setup_env(config: dict) -> None:
    import secrets
    signed = config.get("signed", True)
    fluidkit_registry.signed = signed
    if signed:
        os.environ.setdefault("FLUIDKIT_SECRET", secrets.token_urlsafe(32))


@contextmanager
def _uvicorn_server(app, host: str, port: int, **kwargs):
    """Start uvicorn in a thread, wait for ready, shut down on exit."""
    import uvicorn

    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_config=None, **kwargs))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.1)
    try:
        yield server
    finally:
        server.should_exit = True
        thread.join(timeout=5)


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
    from fluidkit.hooks import hooks
    from fluidkit.codegen import generate
    from fluidkit.explorer import mount, notify_change
    from fluidkit.codegen import watch as codegen_watch
    from fluidkit.cli.scaffold import copy_runtime_files

    _setup_env(config)

    load_entry(config["entry"])
    fluidkit_registry.dev = True
    
    mount(fluidkit_registry.app, fluidkit_registry)
    fluidkit_registry.on_change(notify_change)

    base_url = f"http://{display_host(config)}:{config['backend_port']}"

    copy_runtime_files(schema_output=config["schema_output"])
    generate(fluidkit_registry.functions, base_url=base_url, schema_output=config["schema_output"], signed=config.get("signed", True))
    codegen_watch(fluidkit_registry, base_url=base_url, schema_output=config["schema_output"])

    if hmr:
        import jurigged
        from fluidkit import hmr as hmr_module

        watcher = jurigged.watch(logger=hmr_update, pattern=config["watch_pattern"])
        watch_dir = str(Path(config["entry"]).parent)
        hmr_module.setup(watcher, watch_paths=(watch_dir,))

        for metadata in fluidkit_registry.functions.values():
            hmr_module.attach_conform(metadata)
        echo("fluid", "HMR enabled", _COLORS["warn"])
    else:
        echo("fluid", "HMR disabled", _COLORS["warn"])

    setup_logging()

    for line in hooks._get_summary_lines():
        echo("fluid", line)

    proc = await run_node_tool_async("npm", ["run", npm_command])

    with _uvicorn_server(
        fluidkit_registry.app,
        host=config["host"],
        port=config["backend_port"],
        reload=not hmr,
    ):
        host = display_host(config)
        header_shown = False

        async def _warmup(host: str, port: int, timeout: float = 5.0) -> None:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=timeout,
                )
                writer.write(b"GET / HTTP/1.0\r\nHost: localhost\r\n\r\n")
                await asyncio.wait_for(reader.read(1024), timeout=timeout)
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

        async def _stream_stdout(stream):
            nonlocal header_shown
            async for line in stream:
                text = line.decode(errors="replace").rstrip()
                if not text:
                    continue
                if not header_shown and "ready in" in text:
                    header_shown = True
                    echo("fluid", "warming up vite for first visit...", _COLORS["fluid"])
                    await _warmup("localhost", config['frontend_port'])
                    header(
                        version=__version__,
                        fluid_url=f"http://{host}:{config['backend_port']}",
                        vite_url=f"http://localhost:{config['frontend_port']}",
                    )
                echo("vite", text, _COLORS["vite"])

        try:
            await asyncio.gather(
                _stream_stdout(proc.stdout),
                _stream(proc.stderr, "vite", _COLORS["warn"]),
            )
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            proc.terminate()
            await proc.wait()


def _run_with_header(config: dict, npm_command: str, hmr: bool = False) -> None:
    try:
        asyncio.run(_run_servers(config, npm_command=npm_command, hmr=hmr))
    except KeyboardInterrupt:
        pass


def run_dev(config: dict, hmr: bool = True) -> None:
    _run_with_header(config, "dev", hmr=hmr)


def run_preview(config: dict) -> None:
    _run_with_header(config, "preview", hmr=False)


def run_build(config: dict) -> None:
    from fluidkit.hooks import hooks
    from fluidkit.codegen import generate
    from fluidkit.cli.scaffold import copy_runtime_files

    _setup_env(config)

    load_entry(config["entry"])

    base_url = f"http://localhost:{config['backend_port']}"

    copy_runtime_files(schema_output=config["schema_output"])
    generate(
        functions=fluidkit_registry.functions,
        base_url=base_url,
        schema_output=config["schema_output"],
        signed=config.get("signed", True)
    )
    echo("fluid", "codegen done")

    setup_logging()

    for line in hooks._get_summary_lines():
        echo("fluid", line)

    with _uvicorn_server(
        fluidkit_registry.app,
        host="localhost",
        port=config["backend_port"],
    ):
        run_node_tool("npm", ["run", "build"])
