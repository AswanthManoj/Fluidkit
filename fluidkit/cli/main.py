import typer
from .config import load_config
from .scaffold import scaffold_project
from .process import run_dev, run_build, run_preview
from .patch import patch_svelte_config, patch_vite_config, check_svelte_experimental


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
    no_hmr: bool = typer.Option(False, "--no-hmr", help="Disable HMR, restart on change"),
):
    """Run FluidKit backend + Vite frontend together."""
    config = load_config({"host": host, "backend_port": backend_port, "frontend_port": frontend_port})
    patch_svelte_config(schema_output=config["schema_output"])
    patch_vite_config(frontend_port=config["frontend_port"])
    check_svelte_experimental()
    run_dev(config, hmr=not no_hmr)


@app.command()
def build(
    backend_port: int = typer.Option(None, help="Override backend port"),
):
    """Run codegen then npm run build."""
    config = load_config({"backend_port": backend_port})
    patch_svelte_config(schema_output=config["schema_output"])
    patch_vite_config(frontend_port=config["frontend_port"])
    check_svelte_experimental()
    run_build(config)


@app.command()
def preview(
    backend_port: int = typer.Option(None, help="Override backend port"),
    frontend_port: int = typer.Option(None, help="Override frontend port"),
):
    """Preview the production build locally."""
    config = load_config({"backend_port": backend_port, "frontend_port": frontend_port})
    run_preview(config)


if __name__ == "__main__":
    app()
