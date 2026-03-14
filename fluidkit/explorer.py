import asyncio
import inspect
import logging
from typing import Any
from pathlib import Path
from enum import EnumMeta
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel as PydanticBaseModel

from fluidkit.models import FunctionMetadata, ContainerType
from fluidkit.utilities import generate_route_path, normalize_types, FieldAnnotation


_loop = None
logger = logging.getLogger(__name__)
_STATIC = Path(__file__).parent / "explorer" / "static"


class _ConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self._connections.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self._connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)


_manager = _ConnectionManager()


def _annotation_to_str(ann) -> str:
    if ann.base_type is not None:
        return ann.base_type.value
    if ann.custom_type is not None:
        return ann.custom_type
    if ann.container is not None:
        match ann.container:
            case ContainerType.OPTIONAL:
                return f"{_annotation_to_str(ann.args[0])} | null"
            case ContainerType.ARRAY:
                return f"{_annotation_to_str(ann.args[0])}[]"
            case ContainerType.RECORD:
                return f"Record<{_annotation_to_str(ann.args[0])}, {_annotation_to_str(ann.args[1])}>"
            case ContainerType.TUPLE:
                return f"[{', '.join(_annotation_to_str(a) for a in ann.args)}]"
            case ContainerType.UNION:
                return " | ".join(_annotation_to_str(a) for a in ann.args)
            case ContainerType.LITERAL:
                return " | ".join(repr(v) for v in ann.literal_values)
    return "any"


def _extract_schema(ann: "FieldAnnotation") -> dict | None:
    ref = ann.class_reference
    
    # Unwrap array/optional to get at the inner class_reference
    if ref is None and ann.args:
        return _extract_schema(ann.args[0])

    if ref is None:
        return None

    if isinstance(ref, EnumMeta):
        return {"kind": "enum", "values": [e.value for e in ref]}

    if isinstance(ref, type) and issubclass(ref, PydanticBaseModel):
        fields = []
        for field_name, field_info in ref.model_fields.items():
            field_ann = normalize_types(field_info.annotation)
            fields.append({
                "name": field_name,
                "type": _annotation_to_str(field_ann),
                "required": field_info.is_required(),
                "default": None if field_info.default is inspect.Parameter.empty else _safe_default(field_info.default),
                "schema": _extract_schema(field_ann),
            })
        return {"kind": "object", "fields": fields}

    return None


def _serialize_function(key: str, fn: FunctionMetadata) -> dict:
    return {
        "key": key,
        "name": fn.name,
        "module": fn.module,
        "file_path": fn.file_path,
        "route": generate_route_path(fn),
        "decorator_type": fn.decorator_type.value,
        "docstring": fn.docstring,
        "return_type": _annotation_to_str(fn.return_annotation),
        "parameters": [
            {
                "name": p.name,
                "type": _annotation_to_str(p.annotation),
                "required": p.required,
                "default": None if p.default is inspect.Parameter.empty else _safe_default(p.default),
                "schema": _extract_schema(p.annotation),  # ← add this line
            }
            for p in fn.parameters
        ],
    }


def _safe_default(value: Any) -> Any:
    """Return JSON-safe default or its string representation."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def serialize_all(functions: dict[str, FunctionMetadata]) -> dict:
    return {
        key: _serialize_function(key, fn)
        for key, fn in functions.items()
    }


def serialize_keys(functions: dict[str, FunctionMetadata], keys: list[str]) -> dict:
    return {
        key: _serialize_function(key, functions[key])
        for key in keys
        if key in functions
    }


def notify_change(event: dict):
    """Called from registry on function register/unregister. Thread-safe."""
    if _loop is None:
        return
    payload = {"action": event["action"], "keys": [event["key"]]}
    _loop.call_soon_threadsafe(asyncio.ensure_future, _manager.broadcast(payload))
    

def mount(app, registry):
    """Mount explorer endpoints on the FastAPI app. Call only in dev mode."""

    @app.get("/meta")
    async def get_meta():
        return JSONResponse(serialize_all(registry.functions))

    @app.post("/meta")
    async def get_meta_filtered(body: dict):
        keys = body.get("keys", [])
        return JSONResponse(serialize_keys(registry.functions, keys))

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        global _loop
        if _loop is None:
            _loop = asyncio.get_running_loop()
        await _manager.connect(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            _manager.disconnect(ws)

    if _STATIC.exists():
        @app.get("/")
        async def explorer_index():
            return FileResponse(_STATIC / "index.html")
        app.mount("/assets", StaticFiles(directory=_STATIC / "assets"), name="explorer_assets")
    else:
        @app.get("/")
        async def health():
            from fluidkit import __version__
            return {"status": "running", "version": __version__}

    logger.debug("explorer mounted")
