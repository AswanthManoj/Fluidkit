from importlib.metadata import version

from fluidkit.context import get_request_event
from fluidkit.types import FileUpload, RequestEvent
from fluidkit.exceptions import HTTPError, Redirect, error
from fluidkit.decorators import command, form, prerender, query
from fluidkit.registry import fluidkit_registry, lifespan, on_shutdown, on_startup, preserve


__version__ = version("fluidkit")


app = fluidkit_registry.app


__all__ = [
    "app",
    "form",
    "query",
    "command",
    "prerender",
    "lifespan",
    "preserve",
    "on_startup",
    "on_shutdown",
    "error",
    "Redirect",
    "HTTPError",
    "FileUpload",
    "RequestEvent",
    "get_request_event",
]
