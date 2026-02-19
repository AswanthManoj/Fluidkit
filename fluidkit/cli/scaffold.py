import sys
import typer
from .utils import get_npx, get_npm, _fmt


def scaffold_project():
    npx = get_npx()
    npm = get_npm()

    result = npx(["sv", "create", ".", "--no-dir-check", "--no-install", "--template", "minimal"], return_completed_process=True)
    if result.returncode != 0:
        typer.echo(_fmt("fluidkit", "sv create failed."))
        sys.exit(result.returncode)

    typer.echo(_fmt("fluidkit", "installing dependencies..."))
    result = npm(["install"], return_completed_process=True)
    if result.returncode != 0:
        typer.echo(_fmt("fluidkit", "npm install failed."))
        sys.exit(result.returncode)

    typer.echo(_fmt("fluidkit", "done! run: npm run dev"))
