import typer
from .config import load_config
from .scaffold import scaffold_project
from .process import run_dev, run_build, run_preview
from .patch import patch_svelte_config, patch_vite_config, check_svelte_experimental
from .utils import run_node_tool


app = typer.Typer(help="FluidKit CLI")


def _apply_patches(config: dict) -> None:
    patch_svelte_config(schema_output=config["schema_output"])
    patch_vite_config(frontend_port=config["frontend_port"])
    check_svelte_experimental()


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
    _apply_patches(config)
    run_dev(config, hmr=not no_hmr)


@app.command()
def build(
    backend_port: int = typer.Option(None, help="Override backend port"),
):
    """Build the project for production."""
    config = load_config({"backend_port": backend_port})
    _apply_patches(config)
    run_build(config)


@app.command()
def preview(
    backend_port: int = typer.Option(None, help="Override backend port"),
    frontend_port: int = typer.Option(None, help="Override frontend port"),
):
    """Preview the production build locally."""
    config = load_config({"backend_port": backend_port, "frontend_port": frontend_port})
    run_preview(config)


@app.command(
    context_settings={"allow_extra_args": True, "allow_interspersed_args": False}
)
def npm(ctx: typer.Context):
    """Run any npm command. Usage: fluidkit npm install, fluidkit npm run build, etc."""
    run_node_tool("npm", ctx.args)


@app.command(
    context_settings={"allow_extra_args": True, "allow_interspersed_args": False}
)
def npx(ctx: typer.Context):
    """Run any npx command. Usage: fluidkit npx sv add tailwindcss, fluidkit npx prisma generate, etc."""
    run_node_tool("npx", ctx.args)


@app.command(
    context_settings={"allow_extra_args": True, "allow_interspersed_args": False}
)
def node(ctx: typer.Context):
    """Run node directly. Usage: fluidkit node script.js, fluidkit node --version, etc."""
    run_node_tool("node", ctx.args)


@app.command(
    context_settings={"allow_extra_args": True, "allow_interspersed_args": False}
)
def install(
    ctx: typer.Context,
    dev: bool = typer.Option(False, "-D", "--save-dev", help="Install as dev dependency"),
):
    """Install npm packages. Usage: fluidkit install tailwindcss, fluidkit install -D prettier"""
    args = ["install"] + ctx.args
    if dev:
        args.insert(1, "--save-dev")
    run_node_tool("npm", args)


if __name__ == "__main__":
    app()
