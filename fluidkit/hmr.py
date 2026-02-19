import sys
import types
import logging
from fluidkit.models import FunctionMetadata, FieldAnnotation

logger = logging.getLogger(__name__)


class RemoteFunction:
    __slots__ = ("_code", "_func", "_name", "_params", "_module", "_metadata")

    def __init__(self, func, metadata: FunctionMetadata):
        self._func = func
        self._name = func.__name__
        self._code = func.__code__
        self._params = list(func.__code__.co_varnames[:func.__code__.co_argcount])
        self._module = metadata.module
        self._metadata = metadata

    def __conform__(self, new_func):
        if new_func is None:
            from fluidkit.registry import fluidkit_registry
            key = f"{self._module}#{self._name}"
            if fluidkit_registry.functions.get(key) is self._metadata:
                fluidkit_registry.unregister(self._module, self._name)
                fluidkit_registry._fire_on_register(self._metadata)
            if hasattr(self._func, '_remote_wrapper'):
                del self._func._remote_wrapper
            return

        new_code = getattr(new_func, '__code__', new_func)
        if not isinstance(new_code, types.CodeType):
            return

        if isinstance(new_func, types.CodeType):
            self._code = new_code
            self._params = list(new_code.co_varnames[:new_code.co_argcount])
            return

        new_params = list(new_code.co_varnames[:new_code.co_argcount])
        old_params = self._params
        self._code = new_code
        self._params = new_params
        self._func = new_func

        if old_params != new_params:
            logger.debug("[fluidkit] %s signature updated", self._name)
            from fluidkit.registry import fluidkit_registry
            fluidkit_registry._fire_on_register(self._metadata)


def attach_conform(metadata: FunctionMetadata):
    module = sys.modules.get(metadata.module)
    if module is None:
        return
    module_level = getattr(module, metadata.name, None)
    if module_level is None:
        return
    actual_func = getattr(module_level, '__wrapped__', module_level)
    if hasattr(actual_func, '_remote_wrapper'):
        return
    actual_func._remote_wrapper = RemoteFunction(actual_func, metadata)


def _on_postrun(path: str, cf) -> None:
    from fluidkit.registry import fluidkit_registry
    for metadata in fluidkit_registry.functions.values():
        attach_conform(metadata)


def setup(watcher):
    watcher.postrun.register(_on_postrun)
