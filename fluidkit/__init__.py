import logging
from fluidkit.registry import fluidkit_registry
from fluidkit.types import RequestEvent, FileUpload
from fluidkit.exceptions import HTTPError, Redirect, error
from fluidkit.decorators import query, form, command, prerender


app = fluidkit_registry.app
logger = logging.getLogger(__name__)


def run(host: str = "0.0.0.0", port: int = 8000, dev: bool = False, watch_pattern: str = "src/**/*.py", schema_output: str = "src/lib/fluidkit"):
    fluidkit_registry.configure(dev=dev, host=host, port=port, schema_output=schema_output)
    
    if dev:
        import jurigged
        from fluidkit import hmr
        from fluidkit.codegen import watch as codegen_watch

        codegen_watch(fluidkit_registry)

        watcher = jurigged.watch(pattern=watch_pattern)
        hmr.setup(watcher)

        for metadata in fluidkit_registry.functions.values():
            hmr.attach_conform(metadata)

        logger.info("[fluidkit] dev mode")

    import uvicorn
    uvicorn.run(app, host=host, port=port)



__all__ = [
    'app',
    'run',
    'query',
    'command',
    'form',
    'prerender',
    'error',
    'HTTPError',
    'Redirect',
    'RequestEvent',
    'FileUpload',
]
