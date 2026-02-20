import typer
from .config import load_config
from .scaffold import scaffold_project
from .process import run_dev, run_build
from .patch import patch_svelte_config, patch_vite_config


app = typer.Typer(help="FluidKit CLI")


@app.command()
def init():
    """Scaffold a new FluidKit + SvelteKit project."""
    scaffold_project()


@app.command()
def dev(
    host: str = typer.Option(None, help="Override host"),
    backend_port: int = typer.Option(None, help="Override backend port"),
    frontend_port: int = typer.Option(None, help="Override frontend port"),
):
    """Run FluidKit backend + Vite frontend together."""
    config = load_config({"host": host, "backend_port": backend_port, "frontend_port": frontend_port})
    patch_svelte_config(schema_output=config["schema_output"])
    patch_vite_config(frontend_port=config["frontend_port"])
    run_dev(config)


@app.command()
def build(
    backend_port: int = typer.Option(None, help="Override backend port"),
):
    """Run codegen then npm run build."""
    config = load_config({"backend_port": backend_port})
    patch_svelte_config(schema_output=config["schema_output"])
    patch_vite_config(frontend_port=config["frontend_port"])
    run_build(config)


if __name__ == "__main__":
    app()
