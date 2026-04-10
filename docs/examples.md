# Examples

Standalone patterns you can copy into your project.

## Blog CRUD

A complete read/write flow using all three runtime decorators:

```python
# src/lib/blog.py
from pydantic import BaseModel
from fluidkit import query, command, form, redirect

class Post(BaseModel):
    id: int
    title: str
    content: str
    likes: int = 0

posts: list[Post] = [
    Post(id=1, title="Hello World", content="First post.", likes=3),
]

@query
async def get_posts() -> list[Post]:
    return posts

@query
async def get_post(post_id: int) -> Post | None:
    return next((p for p in posts if p.id == post_id), None)

@form
async def create_post(title: str, content: str) -> None:
    post = Post(id=len(posts) + 1, title=title, content=content)
    posts.append(post)
    await get_posts().refresh()
    redirect(303, "/blog")

@command
async def like_post(post_id: int) -> bool:
    for post in posts:
        if post.id == post_id:
            post.likes += 1
            await get_posts().refresh()
            return True
    return False

@command
async def delete_post(post_id: int) -> None:
    global posts
    posts = [p for p in posts if p.id != post_id]
    await get_posts().refresh()
```

```svelte
<!-- src/routes/blog/+page.svelte -->
<script>
  import { get_posts, like_post, delete_post, create_post } from '$lib/blog.remote';
</script>

<h1>Blog</h1>

<form {...create_post}>
  <input {...create_post.fields.title.as('text')} placeholder="Title" />
  <textarea {...create_post.fields.content.as('text')} placeholder="Content"></textarea>
  <button>Publish</button>
</form>

{#each await get_posts() as post}
  <article>
    <h2>{post.title}</h2>
    <p>{post.content}</p>
    <button onclick={async () => await like_post(post.id)}>👍 {post.likes}</button>
    <button onclick={async () => await delete_post(post.id)}>🗑️ Delete</button>
  </article>
{/each}
```

## Batching queries

Avoid the N+1 problem by batching concurrent queries into a single request:

```python
# src/lib/weather.py
from pydantic import BaseModel
from fluidkit import query, command

class CityWeather(BaseModel):
    city_id: str
    name: str
    temp: float

weather_db: dict[str, CityWeather] = {
    "nyc": CityWeather(city_id="nyc", name="New York", temp=72.0),
    "la":  CityWeather(city_id="la",  name="Los Angeles", temp=85.0),
    "sf":  CityWeather(city_id="sf",  name="San Francisco", temp=60.0),
}

@query.batch
async def get_weather(city_ids: list[str]):
    lookup = {cid: weather_db.get(cid) for cid in city_ids}
    return lambda city_id, idx: lookup.get(city_id)

@command
async def set_temp(city_id: str, temp: float) -> None:
    if city_id in weather_db:
        weather_db[city_id].temp = temp
        await get_weather(city_id).refresh()
```

```svelte
<script>
  import { get_weather, set_temp } from '$lib/weather.remote';

  const cities = ['nyc', 'la', 'sf'];
</script>

{#each cities as id}
  <div>
    {#await get_weather(id) then weather}
      <h3>{weather.name}</h3>
      <p>{weather.temp}°F</p>
      <button onclick={async () => await set_temp(id, weather.temp + 1)}>+1°</button>
    {/await}
  </div>
{/each}
```

All three `get_weather` calls in the `{#each}` block are batched into a single request. Clicking +1° refreshes only that city's data.

## Auth guard with cookies

Read and set cookies via `get_request_event()`:

```python
# src/lib/auth.py
from fluidkit import query, form, command, error, redirect, get_request_event

USERS = {"admin": "secret123"}

@form
async def login(username: str, _password: str) -> None:
    if USERS.get(username) != _password:
        error(401, "Invalid credentials")
    event = get_request_event()
    event.cookies.set("session", username, httponly=True, path="/")
    redirect(303, "/dashboard")

@command
async def logout() -> None:
    event = get_request_event()
    event.cookies.set("session", "", httponly=True, path="/", max_age=0)

@query
async def get_current_user() -> dict | None:
    event = get_request_event()
    username = event.cookies.get("session")
    if not username:
        return None
    return {"username": username}
```

```svelte
<!-- src/routes/login/+page.svelte -->
<script>
  import { login } from '$lib/auth.remote';
</script>

<form {...login}>
  <input {...login.fields.username.as('text')} placeholder="Username" />
  <input {...login.fields._password.as('password')} placeholder="Password" />
  <button>Log in</button>
</form>
```

> Prefix sensitive parameters with an underscore (e.g. `_password`) to prevent them from being sent back to the client on validation failure.

Cookie options like `httponly`, `path`, `max_age`, `secure`, `samesite`, and `domain` are passed through from Python directly to SvelteKit's cookie API.

## File upload

Use `FileUpload` for file handling in forms:

```python
# src/lib/uploads.py
from fluidkit import form, FileUpload

UPLOADS: list[dict] = []

@form
async def upload_file(label: str, attachment: FileUpload) -> dict:
    contents = await attachment.read()
    entry = {
        "label": label,
        "filename": attachment.filename,
        "size": len(contents),
        "content_type": attachment.content_type,
    }
    UPLOADS.append(entry)
    return {"success": True, "filename": attachment.filename}
```

```svelte
<script>
  import { upload_file } from '$lib/uploads.remote';
</script>

<form {...upload_file} enctype="multipart/form-data">
  <input {...upload_file.fields.label.as('text')} placeholder="Label" />
  <input {...upload_file.fields.attachment.as('file')} />
  <button>Upload</button>
</form>

{#if upload_file.result?.success}
  <p>Uploaded: {upload_file.result.filename}</p>
{/if}
```

Add `enctype="multipart/form-data"` to the form when using file inputs. `FileUpload` extends FastAPI's `UploadFile` — all its methods (`read()`, `filename`, `content_type`) are available.

## Pydantic models and type safety

Pydantic models in parameters and return types become TypeScript interfaces automatically:

```python
# src/lib/catalog.py
from enum import Enum
from pydantic import BaseModel
from fluidkit import query

class Category(str, Enum):
    ELECTRONICS = "electronics"
    BOOKS = "books"
    CLOTHING = "clothing"

class Product(BaseModel):
    id: int
    name: str
    price: float
    category: Category
    tags: list[str] = []

class CatalogPage(BaseModel):
    products: list[Product]
    total: int
    page: int

@query
async def get_catalog(page: int = 1, category: Category | None = None) -> CatalogPage:
    ...
```

FluidKit generates:

```typescript
// $fluidkit/schema.ts (auto-generated)
export enum Category {
  ELECTRONICS = "electronics",
  BOOKS = "books",
  CLOTHING = "clothing",
}

export interface Product {
  id: number;
  name: string;
  price: number;
  category: Category;
  tags?: string[];
}

export interface CatalogPage {
  products: Product[];
  total: number;
  page: number;
}
```

The Svelte side gets full autocompletion and type checking with no extra work.

## Using RequestEvent

Access request data via `get_request_event()`. Available in all decorators:

```python
from fluidkit import query, get_request_event

@query
async def get_session_info() -> dict:
    event = get_request_event()
    return {
        "session_id": event.cookies.get("session_id"),
        "locale": event.cookies.get("locale") or "en",
        "url": event.url,
        "method": event.method,
    }
```

`event.url`, `event.method`, and `event.headers` are available in all decorators. `event.cookies.get(name)` reads a cookie. `event.cookies.set(name, value, **kwargs)` sets one — only in `@form` and `@command`. Calling `set` in `@query` or `@prerender` raises `RuntimeError`.

`event.locals` is shared between `@hooks.handle` and the remote function handler. Serializable values set here are forwarded to SvelteKit. See [Hooks](hooks.md).

## Hooks

Manage startup/shutdown tasks and intercept remote function calls:

```python
# src/app.py
from fluidkit import hooks
import aioredis

db = None
redis = None

@hooks.init
async def connect_db():
    global db
    db = await Database.connect("postgresql://...")

@hooks.cleanup
async def disconnect_db():
    await db.close()

@hooks.lifespan
async def manage_redis():
    global redis
    redis = await aioredis.from_url("redis://localhost")
    yield
    await redis.close()

@hooks.handle
async def auth(event, resolve):
    token = event.cookies.get("access_token")
    event.locals["user"] = await verify_token(token)
    return await resolve(event)
```

See [Hooks](hooks.md) for the full reference.

## preserve() for HMR-safe state

During development, FluidKit hot-reloads your Python files on save. This re-executes module-level code, which recreates objects like database connections. Use `preserve()` to keep expensive objects alive across reloads:

```python
# src/lib/services.py
import httpx
from fluidkit import preserve

# Factory — only called once, survives HMR
client = preserve(lambda: httpx.AsyncClient(base_url="https://api.example.com"))

# Direct value — created once, reused on reload
cache = preserve({})
```

`preserve()` accepts a value or a zero-argument callable. If a callable is passed, it is invoked only on the first execution. On subsequent HMR reloads the stored value is returned.

> Don't use `preserve()` for values you want to update during development — those update automatically via HMR. Only use it for objects that must survive re-execution.
