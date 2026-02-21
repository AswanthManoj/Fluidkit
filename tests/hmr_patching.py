import sys
import types
import uvicorn
import jurigged
from pathlib import Path
from fluidkit import app
from fluidkit.codegen import build_schema_ts
from fluidkit.registry import fluidkit_registry
from fluidkit.utilities import generate_route_path
from fluidkit.models import FunctionMetadata, FieldAnnotation
from fluidkit.codegen.remote import generate_remote_files



from pydantic import BaseModel
from fluidkit import query, command

class Address(BaseModel):
    street: str
    city: str
    zip_code: str

class User(BaseModel):
    name: str
    email: str
    address: Address = None


@query
async def get_user(user_id: str, include_email: bool = False) -> User:
    return User(name="Alice", email="alice@example.com")

@command
async def add_like(post_id: str) -> None:
    return {"message": f"Post {post_id} liked!"}

@command
async def delete_post(post_id: str) -> None:
    return {"message": f"Post {post_id} deleted!"}




BASE_URL = "http://localhost:8000"
SCHEMA_OUTPUT = "src/lib/fluidkit"
_startup_complete = False
_pending_attach: list[FunctionMetadata] = []


# ── Codegen ───────────────────────────────────────────────────────────────────

def _has_custom_types(metadata: FunctionMetadata) -> bool:
    def _check(ann: FieldAnnotation) -> bool:
        if ann.class_reference is not None:
            return True
        return any(_check(a) for a in ann.args)
    return (
        _check(metadata.return_annotation) or
        any(_check(p.annotation) for p in metadata.parameters)
    )


def _trigger_codegen(metadata: FunctionMetadata):
    if metadata.file_path:
        functions_for_file = {
            k: v for k, v in fluidkit_registry.functions.items()
            if v.file_path == metadata.file_path
        }
        generate_remote_files(functions_for_file, base_url=BASE_URL)
        print(f"[codegen] regenerated {Path(metadata.file_path).name.replace('.py', '.remote.ts')}")

    if _has_custom_types(metadata):
        schema_ts = build_schema_ts(list(fluidkit_registry.functions.values()))
        schema_path = Path(SCHEMA_OUTPUT) / "schema.ts"
        schema_path.parent.mkdir(parents=True, exist_ok=True)
        schema_path.write_text(schema_ts, encoding="utf-8")
        print(f"[codegen] regenerated schema.ts")


# ── RemoteFunction ────────────────────────────────────────────────────────────

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
            key = f"{self._module}#{self._name}"
            current_meta = fluidkit_registry.functions.get(key)
            if current_meta is self._metadata:
                print(f"[conform] {self._name} — deleted")
                fluidkit_registry.unregister(self._module, self._name)
                _trigger_codegen(self._metadata)
            else:
                print(f"[conform] {self._name} — superseded, skipping unregister")
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
            print(f"[conform] {self._name} — signature changed {old_params} -> {new_params}")
            _trigger_codegen(self._metadata)
        else:
            print(f"[conform] {self._name} — body-only")


# ── Conform attachment ────────────────────────────────────────────────────────

def _attach_conform(metadata: FunctionMetadata):
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
    print(f"[hmr] attached __conform__ to {metadata.module}#{metadata.name}")


def _install_register_patch():
    original_register = fluidkit_registry.register

    def patched_register(metadata: FunctionMetadata, handler):
        # Clean by path before registering — prevents duplicate operation IDs
        # when decorator type changes (@query -> @command) because the route
        # name changes but the path stays the same
        path = generate_route_path(metadata)
        app.router.routes = [
            r for r in app.router.routes
            if getattr(r, 'path', None) != path
        ]
        app.openapi_schema = None

        original_register(metadata, handler)

        if _startup_complete:
            print(f"[hmr] new function registered at runtime: {metadata.name}")
            _trigger_codegen(metadata)
            _pending_attach.append(metadata)

    fluidkit_registry.register = patched_register
    print("[hmr] patched fluidkit_registry.register")


# ── Watcher callbacks ─────────────────────────────────────────────────────────

def _on_prerun(path: str, cf) -> None:
    print(f"About to patch: {path}")


def _on_postrun(path: str, cf) -> None:
    print(f"Patched: {path}")
    while _pending_attach:
        _attach_conform(_pending_attach.pop(0))


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _install_register_patch()

    for metadata in fluidkit_registry.functions.values():
        _attach_conform(metadata)

    _startup_complete = True

    watcher = jurigged.watch()
    watcher.prerun.register(_on_prerun)
    watcher.postrun.register(_on_postrun)
    print("[fluid] watching")
    uvicorn.run(app, host="0.0.0.0", port=8000)
