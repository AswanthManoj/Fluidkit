import sys
import typer


def get_npx():
    try:
        from nodejs_wheel import npx
        return npx
    except ImportError:
        typer.echo(_fmt("fluidkit", "nodejs-wheel is not installed. Run: pip install nodejs-wheel"))
        sys.exit(1)


def get_npm():
    try:
        from nodejs_wheel import npm
        return npm
    except ImportError:
        typer.echo(_fmt("fluidkit", "nodejs-wheel is not installed. Run: pip install nodejs-wheel"))
        sys.exit(1)


def _fmt(prefix: str, line: str) -> str:
    colors = {
        "fluidkit": typer.colors.BRIGHT_CYAN,
        "vite":     typer.colors.BRIGHT_GREEN,
    }
    return typer.style(f"  [{prefix}]", fg=colors[prefix], bold=True) + f" {line}"
