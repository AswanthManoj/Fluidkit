# Hooks

FluidKit hooks let you run Python code at server lifecycle points and intercept every remote function call — without writing any TypeScript. They mirror SvelteKit's `hooks.server.ts` behavior but live entirely in Python.

```python
from fluidkit import hooks
```

---

## Lifecycle

### @hooks.init

Runs once when the server starts. Async or sync, no parameters.

```python
@hooks.init
async def setup():
    global db
    db = await Database.connect("postgresql://...")
```

### @hooks.cleanup

Runs once when the server shuts down. Async or sync, no parameters.

```python
@hooks.cleanup
async def teardown():
    await db.close()
```

### @hooks.lifespan

Paired setup and teardown via a generator. Code before `yield` runs at startup, code after runs at shutdown. Async or sync generator, no parameters, yields exactly once.

```python
@hooks.lifespan
async def manage_redis():
    global redis
    redis = await aioredis.from_url("redis://localhost")
    yield
    await redis.close()
```

Only one `@hooks.init`, one `@hooks.cleanup`, and one `@hooks.lifespan` are allowed per application. Registering a second one from the same module replaces the first with a warning. Registering from a different module raises `RuntimeError`.

---

## Request middleware — @hooks.handle

Runs on every remote function call. Receives `(event, resolve)`. Must return `await resolve(event)` to continue, or return early to short-circuit.

```python
from fluidkit import hooks, error

@hooks.handle
async def auth(event, resolve):
    token = event.cookies.get("access_token")
    if not token:
        error(401, "Unauthorized")
    event.locals["user"] = await verify_token(token)
    return await resolve(event)
```

```python
@hooks.handle
async def logging(event, resolve):
    import time
    start = time.time()
    result = await resolve(event)
    print(f"{event.method} {event.url} — {time.time() - start:.2f}s")
    return result
```

Multiple `@hooks.handle` hooks are allowed. Default order is source order within a file, then file import order across files.

### Ordering

Use `hooks.sequence()` to set explicit execution order. Each function must already be decorated with `@hooks.handle`. Only one `sequence()` call is allowed per application — calling it from a second module raises `RuntimeError`. Calling it again from the same module replaces the previous order.

```python
hooks.sequence(auth, logging)
```

### HookEvent reference

The `event` object passed to every `@hooks.handle` handler:

| Field | Type | Description |
|---|---|---|
| `event.url` | `str` | Full request URL |
| `event.method` | `str` | HTTP method |
| `event.headers` | `dict[str, str]` | Incoming request headers |
| `event.cookies` | `Cookies` | Shared with the remote function handler. Reads and writes are collected together. |
| `event.locals` | `_LocalsDict` | Shared with the remote function handler. Serializable values are forwarded to SvelteKit. |
| `event.is_remote` | `bool` | `True` for remote function calls, `False` for page-level requests |

`event.cookies` and `event.locals` are the same instances shared with `RequestEvent` inside the remote function. A value set in a hook is visible inside the handler and vice versa.

Sync handle hooks run in a thread executor automatically.

---

## Error hooks

Error hooks fire for unexpected exceptions only. `error()` (HTTPError) and `redirect()` are intentional control flow and never reach these hooks.

### @hooks.handle_error

Fires for:
- `TypeError` — wrong argument types (status 400)
- `ValueError` — invalid data in `@form` (status 400), unhandled elsewhere (status 500)
- Any other unhandled `Exception` (status 500)

Must accept four parameters: `(error, event, status, message)`. Must return a dict with at minimum `{"message": str}`. The returned dict becomes the full JSON response body at the corresponding status code.

```python
@hooks.handle_error
async def on_error(error, event, status, message):
    error_id = str(uuid4())
    logger.exception(error, extra={"error_id": error_id})
    return {"message": "Something went wrong", "error_id": error_id}
```

### @hooks.handle_validation_error

Fires when a remote function parameter fails pydantic schema validation (status 400). Does not fire for other error types.

Must accept two parameters: `(issues, event)` where `issues` is pydantic's `e.errors()` structured list. Must return a dict with at minimum `{"message": str}`.

```python
@hooks.handle_validation_error
async def on_validation_error(issues, event):
    first = issues[0] if issues else {}
    field = first.get("loc", ("input",))[-1]
    return {"message": f"Invalid value for field: {field}"}
```

Only one of each is allowed per application. If either hook itself raises, the default error response is used silently.

---

## Generated src/hooks.server.ts

When any hooks are registered, FluidKit automatically generates `src/hooks.server.ts`. Do not edit it — FluidKit overwrites it on every `dev` and `build`. If you need additional SvelteKit server handle logic, use SvelteKit's `sequence()` helper in a separate file.

If no hooks are registered and this file was previously generated by FluidKit, it is removed automatically.

<details>
<summary>How it works internally</summary>

The generated file installs a SvelteKit `handle` export that POST's to `/__fk_hooks__` before every page request. The Python server runs your `@hooks.handle` chain and returns cookies and locals piggybacked on the response. Cookies are applied via `event.cookies.set()` and locals are merged into `event.locals` before the page renders — which is why cookie writes from handle hooks work correctly even for `@query` and `@prerender`.
</details>

---

## Deprecated API

`@on_startup`, `@on_shutdown`, and `@lifespan` imported directly from `fluidkit` still work but emit `DeprecationWarning` at decoration time.

| Deprecated | Replacement |
|---|---|
| `from fluidkit import on_startup` | `@hooks.init` |
| `from fluidkit import on_shutdown` | `@hooks.cleanup` |
| `from fluidkit import lifespan` | `@hooks.lifespan` |

```python
# Before
from fluidkit import on_startup, on_shutdown

@on_startup
async def setup():
    global db
    db = await Database.connect("postgresql://...")

@on_shutdown
async def teardown():
    await db.close()

# After
from fluidkit import hooks

@hooks.init
async def setup():
    global db
    db = await Database.connect("postgresql://...")

@hooks.cleanup
async def teardown():
    await db.close()
```
