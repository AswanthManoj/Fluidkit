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

def _get_node_tool(name: str):
    try:
        import nodejs_wheel
        return getattr(nodejs_wheel, name)
    except ImportError:
        echo("fluid", "nodejs-wheel is not installed. Run: pip install nodejs-wheel", _COLORS["error"])
        sys.exit(1)


def get_npx():
    return _get_node_tool("npx")


def get_npm():
    return _get_node_tool("npm")


def display_host(config: dict) -> str:
    return "localhost" if config["host"] == "0.0.0.0" else config["host"]
