import re
import sys
import typer
import logging


# ── Colors ────────────────────────────────────────────────────────────────────

_COLORS = {
    "error":  typer.colors.BRIGHT_RED,
    "hmr":    typer.colors.BRIGHT_BLUE,
    "fluid":  typer.colors.BRIGHT_CYAN,
    "vite":   typer.colors.BRIGHT_GREEN,
    "warn":   typer.colors.BRIGHT_YELLOW,
}


# ── Single output authority ───────────────────────────────────────────────────

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
    if op_str.startswith("Run"):
        color = _COLORS["hmr"]
    elif op_str.startswith("Delete"):
        color = _COLORS["error"]
    else:
        color = _COLORS["vite"]
    typer.echo(
        typer.style("  [fluid] ", fg=_COLORS["fluid"], bold=True)
        + typer.style("hmr update", fg=color)
        + f" {op}"
    )


# ── Logging ───────────────────────────────────────────────────────────────────

class _FluidKitLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        msg = self.format(record)
        if re.search(r'" 2\d{2}', msg):
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
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "jurigged"):
        log = logging.getLogger(name)
        log.handlers = [handler]
        log.propagate = False
        if log.level == logging.NOTSET:
            log.setLevel(logging.DEBUG)


# ── Node helpers ──────────────────────────────────────────────────────────────

def get_node_tool(name: str):
    """Get a nodejs-wheel tool callable (npm, npx, node) or exit with install instructions."""
    try:
        import nodejs_wheel
        return getattr(nodejs_wheel, name)
    except ImportError:
        echo("fluid", "nodejs-wheel is not installed. Run: pip install nodejs-wheel", _COLORS["error"])
        sys.exit(1)


def run_node_tool(name: str, args: list[str]) -> None:
    """Run an npm/npx/node command via nodejs-wheel, forwarding exit code."""
    tool = get_node_tool(name)
    result = tool(args, return_completed_process=True)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


async def run_node_tool_async(name: str, args: list[str]):
    """
    Start an npm/npx/node command as an async subprocess.
    Spawns via sys.executable so it works cross-platform,
    including Windows where npm is a .cmd batch file.
    """
    import asyncio
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
