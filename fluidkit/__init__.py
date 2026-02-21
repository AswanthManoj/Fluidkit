from importlib.metadata import version
from fluidkit.context import get_request_event
from fluidkit.registry import fluidkit_registry
from fluidkit.types import RequestEvent, FileUpload
from fluidkit.exceptions import HTTPError, Redirect, error
from fluidkit.decorators import query, form, command, prerender


__version__ = version("fluidkit")


app = fluidkit_registry.app


__all__ = [
    'app',

    'form',
    'query',
    'command',
    'prerender',

    'error',
    'Redirect',
    'HTTPError',
    'FileUpload',
    'RequestEvent',
    'get_request_event',
]
