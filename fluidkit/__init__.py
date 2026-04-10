import warnings
from fluidkit.hooks import hooks
from importlib.metadata import version
from fluidkit.context import get_request_event
from fluidkit.types import FileUpload, RequestEvent
from fluidkit.registry import fluidkit_registry, preserve
from fluidkit.decorators import command, form, prerender, query
from fluidkit.exceptions import HTTPError, Redirect, error, redirect


__version__ = version("fluidkit")


app = fluidkit_registry.app


def on_startup(func):
    """Deprecated: use @hooks.init instead."""
    warnings.warn(
        "@on_startup is deprecated, use @hooks.init instead. "
        "See https://fluidkit.github.io/docs/hooks",
        DeprecationWarning,
        stacklevel=2,
    )
    return hooks.init(func)


def on_shutdown(func):
    """Deprecated: use @hooks.cleanup instead."""
    warnings.warn(
        "@on_shutdown is deprecated, use @hooks.cleanup instead. "
        "See https://fluidkit.github.io/docs/hooks",
        DeprecationWarning,
        stacklevel=2,
    )
    return hooks.cleanup(func)


def lifespan(func):
    """Deprecated: use @hooks.lifespan instead."""
    warnings.warn(
        "@lifespan is deprecated, use @hooks.lifespan instead. "
        "See https://fluidkit.github.io/docs/hooks",
        DeprecationWarning,
        stacklevel=2,
    )
    return hooks.lifespan(func)


__all__ = [
    "app",
    "form",
    "hooks",
    "query",
    "command",
    "prerender",
    "lifespan",
    "preserve",
    "on_startup",
    "on_shutdown",
    "error",
    "redirect",
    "Redirect",
    "HTTPError",
    "FileUpload",
    "RequestEvent",
    "get_request_event",
    "__version__"
]
