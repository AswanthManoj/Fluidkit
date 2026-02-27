from importlib.metadata import version
from fluidkit.context import get_request_event
from fluidkit.types import RequestEvent, FileUpload
from fluidkit.exceptions import HTTPError, Redirect, error
from fluidkit.decorators import query, form, command, prerender
from fluidkit.registry import fluidkit_registry, preserve, on_shutdown, on_startup, lifespan


__version__ = version("fluidkit")


app = fluidkit_registry.app


__all__ = [
    'app',

    'form',
    'query',
    'command',
    'prerender',

    'lifespan',
    'preserve',
    'on_startup',
    'on_shutdown',

    'error',
    'Redirect',
    'HTTPError',
    'FileUpload',
    'RequestEvent',
    'get_request_event',
]
