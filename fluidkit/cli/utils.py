import re
import sys
import typer
import logging
from pathlib import Path



_COLORS = {
    "hmr": typer.colors.BRIGHT_BLUE,
    "error": typer.colors.BRIGHT_RED,
    "fluid": typer.colors.BRIGHT_CYAN,
    "vite": typer.colors.BRIGHT_GREEN,
    "warn": typer.colors.BRIGHT_YELLOW,
}


def echo(prefix: str, line: str, color: str = None) -> None:
    fg = color or _COLORS.get(prefix, typer.colors.BRIGHT_CYAN)
    typer.echo(typer.style(f"  [{prefix}]", fg=fg, bold=True) + f" {line}")


def header(version: str, fluid_url: str, vite_url: str) -> None:
    typer.echo(typer.style(f"\n  fluidkit v{version}\n", fg=_COLORS["fluid"], bold=True))
    typer.echo("  → " + typer.style("[fluid]", fg=_COLORS["fluid"], bold=True) + f"  {fluid_url}")
    typer.echo("  → " + typer.style("[vite] ", fg=_COLORS["vite"], bold=True) + f"  {vite_url}\n")


def hmr_update(op: str) -> None:
    op_str = str(op)
    if op_str.startswith("Watch"):
        return

    parts = op_str.split()
    if len(parts) >= 2:
        module_root = parts[1].split(".")[0]
        mod = sys.modules.get(module_root)
        if mod:
            mod_file = getattr(mod, "__file__", "") or ""
            if "site-packages" in mod_file or ".venv" in mod_file:
                return

    if op_str.startswith("Run"):
        color = _COLORS["hmr"]
    elif op_str.startswith("Delete"):
        color = _COLORS["error"]
    else:
        color = _COLORS["vite"]
    typer.echo(
        typer.style("  [fluid] ", fg=_COLORS["fluid"], bold=True) + typer.style("hmr update", fg=color) + f" {op}"
    )


class _FluidKitLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        msg = self.format(record)
        if re.search(r'" 2\d{2}', msg):
            return
        if "/remote/" in msg and re.search(r'" [345]\d{2}', msg):
            return
        if record.levelno >= logging.ERROR:
            echo("fluid", msg, _COLORS["error"])
        elif record.levelno >= logging.WARNING:
            echo("fluid", msg, _COLORS["warn"])
        else:
            echo("fluid", msg)


def setup_logging() -> None:
    fmt = logging.Formatter("%(message)s")
    handler = _FluidKitLogHandler()
    handler.setFormatter(fmt)
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "jurigged", "fluidkit"):
        log = logging.getLogger(name)
        log.handlers = [handler]
        log.propagate = False
        if log.level == logging.NOTSET:
            log.setLevel(logging.INFO)


def _get_node_bin(name: str) -> str | None:
    """Get the actual binary path from nodejs-wheel, or None."""
    try:
        import nodejs_wheel

        bin_dir = Path(nodejs_wheel.__file__).parent / "bin"
        if sys.platform == "win32":
            for ext in (".cmd", ".exe", ""):
                candidate = bin_dir / f"{name}{ext}"
                if candidate.exists():
                    return str(candidate)
        else:
            candidate = bin_dir / name
            if candidate.exists():
                return str(candidate)
    except (ImportError, AttributeError):
        pass
    return None


def _get_node_tool(name: str):
    """Get a nodejs-wheel tool callable or exit with install instructions."""
    try:
        import nodejs_wheel
        return getattr(nodejs_wheel, name)
    except ImportError:
        echo("fluid", "nodejs-wheel is not installed. Run: pip install nodejs-wheel", _COLORS["error"])
        sys.exit(1)


def _run_node_tool_raw(name: str, args: list[str]):
    """Spawn a node tool directly via binary, falling back to nodejs-wheel. Returns CompletedProcess."""
    import subprocess

    bin_path = _get_node_bin(name)
    if bin_path:
        if sys.platform == "win32" and bin_path.endswith(".cmd"):
            return subprocess.run(["cmd", "/c", bin_path, *args])
        return subprocess.run([bin_path, *args])

    return _get_node_tool(name)(args, return_completed_process=True)


def ensure_node_modules() -> None:
    """Auto-install npm dependencies if node_modules is missing."""
    if not Path("node_modules").exists():
        echo("fluid", "node_modules not found, running npm install...", _COLORS["warn"])
        run_node_tool("npm", ["install"])


def run_node_tool(name: str, args: list[str]) -> None:
    """Run a node tool, raising SystemExit on non-zero exit code."""
    result = _run_node_tool_raw(name, args)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def run_node_tool_checked(name: str, args: list[str]):
    """Run a node tool and return CompletedProcess. Caller handles the exit code."""
    return _run_node_tool_raw(name, args)


async def run_node_tool_async(name: str, args: list[str]):
    """
    Start a node tool as an async subprocess.
    Tries to spawn the binary directly for speed.
    Falls back to Python subprocess for compatibility.
    """
    import asyncio

    bin_path = _get_node_bin(name)
    if bin_path:
        if sys.platform == "win32" and bin_path.endswith(".cmd"):
            return await asyncio.create_subprocess_exec(
                "cmd", "/c", bin_path, *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        return await asyncio.create_subprocess_exec(
            bin_path, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    arg_list = ", ".join(repr(a) for a in args)
    script = (
        f"import sys; import nodejs_wheel; "
        f"sys.exit(nodejs_wheel.{name}([{arg_list}], return_completed_process=True).returncode)"
    )
    return await asyncio.create_subprocess_exec(
        sys.executable, "-c", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


def display_host(config: dict) -> str:
    return "localhost" if config["host"] == "0.0.0.0" else config["host"]


def ensure_undici() -> None:
    if not Path("node_modules/undici").exists():
        echo("fluid", "undici not found, installing...", _COLORS["warn"])
        run_node_tool("npm", ["install", "undici"])
