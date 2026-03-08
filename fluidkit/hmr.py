import ast
import logging
import queue
import sys
import threading
import types
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Module-level state ────────────────────────────────────────────────────────

_route_lock = threading.Lock()
_watch_paths: tuple[str, ...] = ("./",)
_pending_attach: queue.Queue = queue.Queue()
_binding_map: dict[str, list[tuple[str, str]]] = {}


# ── Route safety ──────────────────────────────────────────────────────────────


def _schedule_route_op(op):
    with _route_lock:
        op()


# ── Utils ─────────────────────────────────────────────────────────────────────


def _is_user_module(filename: str) -> bool:
    if not filename or "site-packages" in filename:
        return False
    resolved = str(Path(filename).resolve())
    return any(resolved.startswith(str(Path(p).resolve())) for p in _watch_paths)


def _module_name_from_path(filepath: str) -> str | None:
    if ".venv" in filepath:
        return None
    resolved = str(Path(filepath).resolve()).lower()
    for name, mod in sys.modules.items():
        file = getattr(mod, "__file__", None)
        if file and str(Path(file).resolve()).lower() == resolved:
            return name
    return None


def _resolve_module(node_module: str, node_level: int, importing_module: str) -> str:
    """Resolve a possibly-relative import node to its absolute module name."""
    if node_level == 0:
        return node_module
    parts = importing_module.split(".")
    parent = ".".join(parts[:-node_level]) if node_level < len(parts) else ""
    if parent and node_module:
        return f"{parent}.{node_module}"
    return parent or node_module


# ── Binding tracker ───────────────────────────────────────────────────────────


def _track_imports(module_name: str, filename: str):
    if not _is_user_module(filename) or not filename.endswith(".py"):
        return
    try:
        source = Path(filename).read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception:
        return

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue

        resolved_module = _resolve_module(node.module or "", node.level, module_name)
        if not resolved_module:
            continue

        if any(alias.name == "*" for alias in node.names):
            logger.warning(
                "fluidkit hmr: '%s' uses 'from %s import *' — "
                "variable changes in %s will not hot-reload. "
                "Use explicit imports instead.",
                module_name,
                resolved_module,
                resolved_module,
            )
            continue

        for alias in node.names:
            key = f"{resolved_module}#{alias.name}"
            entry = (module_name, alias.asname or alias.name)
            _binding_map.setdefault(key, [])
            if entry not in _binding_map[key]:
                _binding_map[key].append(entry)


def _rebind_changed(source_module: str):
    src = sys.modules.get(source_module)
    if src is None:
        return

    for attr_name in list(vars(src)):
        if attr_name.startswith("_"):
            continue
        value = getattr(src, attr_name, None)
        if callable(value) and not isinstance(value, type):
            continue

        key = f"{source_module}#{attr_name}"
        if key not in _binding_map:
            continue

        for importing_module, local_name in _binding_map[key]:
            mod = sys.modules.get(importing_module)
            if mod is None or getattr(mod, local_name, None) is value:
                continue
            setattr(mod, local_name, value)
            logger.debug("rebound %s.%s <- %s.%s", importing_module, local_name, source_module, attr_name)


# ── Relative import fix ───────────────────────────────────────────────────────
# Jurigged loses __package__ context when exec-ing individual changed statements.
# This patches Statement.evaluate to always restore it, so `from .x import y`
# resolves correctly instead of raising ModuleNotFoundError.


def _patch_jurigged_for_relative_imports():
    import jurigged.codetools as jct

    original_evaluate = jct.LineDefinition.evaluate

    def patched_evaluate(self, glb, lcl):
        module_name = glb.get("__name__", "")
        mod = sys.modules.get(module_name)
        if mod and "." in module_name:
            if not glb.get("__package__"):
                glb["__package__"] = module_name.rsplit(".", 1)[0]
            if not glb.get("__spec__"):
                spec = getattr(mod, "__spec__", None)
                if spec:
                    glb["__spec__"] = spec
        return original_evaluate(self, glb, lcl)

    jct.LineDefinition.evaluate = patched_evaluate


# ── HMRProxy ──────────────────────────────────────────────────────────────────


class HMRProxy:
    __slots__ = ("_code", "_func", "_name", "_params", "_module", "_metadata")

    def __init__(self, func, metadata):
        self._func = func
        self._name = func.__name__
        self._code = func.__code__
        self._params = list(func.__code__.co_varnames[: func.__code__.co_argcount])
        self._module = metadata.module
        self._metadata = metadata

    def __conform__(self, new_func):
        from fluidkit.registry import fluidkit_registry

        if new_func is None:
            key = f"{self._module}#{self._name}"
            if fluidkit_registry.functions.get(key) is self._metadata:
                module, name, metadata = self._module, self._name, self._metadata

                def op():
                    fluidkit_registry.unregister(module, name)
                    fluidkit_registry._fire_on_register(metadata)

                _schedule_route_op(op)
            if hasattr(self._func, "_hmr_proxy"):
                del self._func._hmr_proxy
            return

        new_code = getattr(new_func, "__code__", new_func)
        if not isinstance(new_code, types.CodeType):
            return

        if isinstance(new_func, types.CodeType):
            self._code = new_code
            self._params = list(new_code.co_varnames[: new_code.co_argcount])
            return

        new_params = list(new_code.co_varnames[: new_code.co_argcount])
        old_params = self._params
        self._code = new_code
        self._params = new_params
        self._func = new_func

        if old_params != new_params:
            fluidkit_registry._fire_on_register(self._metadata)


# ── Conform attachment ────────────────────────────────────────────────────────


def attach_conform(metadata):
    module = sys.modules.get(metadata.module)
    if module is None:
        return
    module_level = getattr(module, metadata.name, None)
    if module_level is None:
        return
    actual_func = getattr(module_level, "__wrapped__", module_level)
    if hasattr(actual_func, "_hmr_proxy"):
        return
    actual_func._hmr_proxy = HMRProxy(actual_func, metadata)


# ── Registry patch ────────────────────────────────────────────────────────────


def _patch_registry(registry):
    original_register = registry.register

    def safe_register(metadata, handler):
        def op():
            original_register(metadata, handler)

        _schedule_route_op(op)
        _pending_attach.put(metadata)

    registry.register = safe_register


# ── Watcher callbacks ─────────────────────────────────────────────────────────


def _on_postrun(path: str, cf) -> None:
    module_name = _module_name_from_path(path)
    if module_name:
        _track_imports(module_name, path)  # re-parse — picks up newly added imports
        _rebind_changed(module_name)
    while not _pending_attach.empty():
        try:
            attach_conform(_pending_attach.get_nowait())
        except queue.Empty:
            break


# ── Setup ─────────────────────────────────────────────────────────────────────


def setup(watcher, watch_paths: tuple[str, ...] = ("./",)):
    global _watch_paths
    _watch_paths = watch_paths

    _patch_jurigged_for_relative_imports()  # must be before jurigged watches anything

    from jurigged import registry as jurigged_registry
    from jurigged.register import add_sniffer

    from fluidkit.registry import fluidkit_registry

    _patch_registry(fluidkit_registry)

    for mod_name, mod in list(sys.modules.items()):
        filename = getattr(mod, "__file__", None)
        if filename:
            _track_imports(mod_name, filename)

    jurigged_registry.auto_register(
        filter=lambda f: (
            f.endswith(".py")
            and ".venv" not in f
            and "site-packages" not in f
            and str(Path(f).resolve()).startswith(str(Path("./").resolve()))
        )
    )

    add_sniffer(_track_imports)

    watcher.postrun.register(_on_postrun)
