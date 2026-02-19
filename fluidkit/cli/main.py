import json
import typer
from pathlib import Path
from .scaffold import scaffold_project
from .utils import _fmt

app = typer.Typer(help="FluidKit CLI")

DEFAULT_CONFIG = {
    "host": "0.0.0.0",
    "port": 8000,
    "vite_port": 5173,
    "schema_output": "src/lib/fluidkit",
}


def load_config(overrides: dict) -> dict:
    config = DEFAULT_CONFIG.copy()
    config_path = Path("fluidkit.config.json")
    if config_path.exists():
        config.update(json.loads(config_path.read_text()))
    config.update({k: v for k, v in overrides.items() if v is not None})
    return config


@app.command()
def init():
    """Scaffold a new FluidKit + SvelteKit project."""
    scaffold_project()


@app.command()
def dev(
    entry: str = typer.Argument("src/main.py"),
    host: str  = typer.Option(None, help="Server host"),
    port: int  = typer.Option(None, help="Server port"),
):
    config = load_config({"host": host, "port": port})
    display_host = "localhost" if config["host"] == "0.0.0.0" else config["host"]

    typer.echo(typer.style("\n  fluidkit v0.1.0\n", fg=typer.colors.BRIGHT_CYAN, bold=True))
    typer.echo("  → " + typer.style("[fluidkit]", fg=typer.colors.BRIGHT_CYAN, bold=True) + f"  http://{display_host}:{config['port']}")
    typer.echo("  → " + typer.style("[vite]    ", fg=typer.colors.BRIGHT_GREEN, bold=True) + f"  http://localhost:{config['vite_port']}\n")


if __name__ == "__main__":
    app()
