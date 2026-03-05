# Remote Functions

FluidKit provides four decorators for defining server-side functions. Each maps to a SvelteKit [remote function](https://svelte.dev/docs/kit/remote-functions) type. Decorate a Python function — FluidKit handles endpoint registration, TypeScript codegen, and client-side wiring.

All decorated functions must be `async` and should use type annotations. Parameters and return values must be serializable — primitives, Pydantic models, or standard types like `list`, `dict`, and `Optional`. Unannotated parameters generate `any` in TypeScript, losing type safety.

## @query

Read data. Cached on the client, refreshable on demand. Supports batching for concurrent calls.

```python
from fluidkit import query
from pydantic import BaseModel

class Post(BaseModel):
    id: int
    title: str
    likes: int

@query
async def get_posts() -> list[Post]:
    return await db.get_all_posts()

@query.batch
async def get_post_likes(post_ids: list[int]):
    likes = await db.get_likes_bulk(post_ids)
    lookup = {row.post_id: row.likes for row in likes}
    return lambda post_id, idx: lookup.get(post_id, 0)
```

→ [Full @query documentation](query.md)

## @form

Write data via `<form>` elements. Supports file uploads, progressive enhancement (works without JavaScript), and redirects.

```python
from fluidkit import form, Redirect

@form
async def create_post(title: str, content: str) -> None:
    slug = await db.insert(title, content)
    raise Redirect(303, f"/blog/{slug}")
```

→ [Full @form documentation](form.md)

## @command

Write data from anywhere — event handlers, button clicks, any imperative call. Use when you're not tied to a `<form>` element.

```python
from fluidkit import command

@command
async def like_post(post_id: int) -> bool:
    return await db.increment_likes(post_id)
```

→ [Full @command documentation](command.md)

## @prerender

Fetch data at build time. Use for content that changes only per deployment.

```python
from fluidkit import prerender
from pydantic import BaseModel

class Page(BaseModel):
    slug: str
    title: str
    body: str

@prerender(inputs=["about", "contact"])
async def get_page(slug: str) -> Page:
    return await db.get_page(slug)
```

→ [Full @prerender documentation](prerender.md)

## Choosing a decorator

| | Read data | Write data | Works without JS | File uploads | Redirects | Batching |
|---|---|---|---|---|---|---|
| `@query` | ✓ | | | | | ✓ |
| `@form` | | ✓ | ✓ | ✓ | ✓ | |
| `@command` | | ✓ | | | | |
| `@prerender` | ✓ (build-time) | | | | | |

## Type annotations

Always annotate your parameters and return types. FluidKit uses them to generate TypeScript types and validate incoming data.

```python
# Good — full type safety on the Svelte side
@query
async def get_post(slug: str) -> Post:
    ...

# Works, but Svelte side sees (slug: any) => any
@query
async def get_post(slug):
    ...
```

For complex types, use Pydantic models. FluidKit generates corresponding TypeScript interfaces automatically:

```python
class PostFilter(BaseModel):
    tag: str | None = None
    limit: int = 10

@query
async def get_posts(filter: PostFilter) -> list[Post]:
    ...
```
