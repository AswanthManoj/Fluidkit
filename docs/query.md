# @query

Use `@query` to read data from the server. Queries are cached on the client and can be refreshed on demand.

## Basic usage

```python
# src/lib/posts.py
from fluidkit import query

@query
async def get_posts():
    return [
        {"id": 1, "title": "Hello World"},
        {"id": 2, "title": "FluidKit"},
    ]
```

The query works as a promise that you can `await` directly in a Svelte component:

```svelte
<script>
  import { get_posts } from '$lib/posts.remote';
</script>

<ul>
  {#each await get_posts() as post}
    <li>{post.title}</li>
  {/each}
</ul>
```

Until the promise resolves — and if it errors — the nearest [`<svelte:boundary>`](https://svelte.dev/docs/svelte/svelte-boundary) will be invoked.

While using `await` is recommended, the query also has `loading`, `error` and `current` properties:

```svelte
<script>
  import { get_posts } from '$lib/posts.remote';

  const posts = get_posts();
</script>

{#if posts.error}
  <p>Something went wrong.</p>
{:else if posts.loading}
  <p>Loading...</p>
{:else}
  <ul>
    {#each posts.current as post}
      <li>{post.title}</li>
    {/each}
  </ul>
{/if}
```

## Arguments

Query functions can accept typed arguments:

```python
from fluidkit import query, error

@query
async def get_post(slug: str):
    post = db.get(slug)
    if not post:
        error(404, "Not found")
    return post
```

```svelte
<script>
  import { get_post } from '$lib/posts.remote';

  let { params } = $props();
  const post = $derived(await get_post(params.slug));
</script>

<h1>{post.title}</h1>
<div>{@html post.content}</div>
```

Arguments are validated by Python's type hints. FluidKit extracts the types from your function signature and generates the corresponding TypeScript types — no manual schema needed. For richer validation, use Pydantic models:

```python
from pydantic import BaseModel

class PostFilter(BaseModel):
    tag: str | None = None
    limit: int = 10

@query
async def get_posts(filter: PostFilter):
    ...
```

FluidKit generates a TypeScript interface for `PostFilter` automatically and uses it in the generated `.remote.ts` file.

## Return types

Annotate your return type and FluidKit will reflect it into TypeScript:

```python
from pydantic import BaseModel

class Post(BaseModel):
    id: int
    title: str
    content: str
    likes: int

@query
async def get_posts() -> list[Post]:
    ...
```

The Svelte side gets full type safety — `post.title` autocompletes, `post.nonexistent` errors at build time. If you omit the return annotation, the generated type will be `any`.

## Errors

Call `error()` to return an HTTP error to the client:
```python
from fluidkit import query, error

@query
async def get_post(slug: str):
    post = await db.find(slug)
    if not post:
        error(404, "Not found")
    return post
```

When using `await` in templates, this triggers the nearest [`<svelte:boundary>`](https://svelte.dev/docs/svelte/svelte-boundary). If you're using the `loading` / `error` / `current` properties instead, the error is available via the `error` property on the query.

## Refreshing queries

Any query can be refetched from the client via its `refresh` method:

```svelte
<button onclick={() => get_posts().refresh()}>
  Check for new posts
</button>
```

Queries are cached while they're on the page, meaning `get_posts() === get_posts()`. You don't need to store a reference to update it.

## Batching

When multiple components each call the same query with different arguments, each call normally results in a separate request. `@query.batch` solves this by collecting concurrent calls into a single request.

```python
from fluidkit import query

@query.batch
async def get_post_likes(post_ids: list[int]):
    likes = await db.get_likes_bulk(post_ids)
    lookup = {row.post_id: row.likes for row in likes}
    return lambda post_id, idx: lookup.get(post_id, 0)
```

The function receives a list of all the arguments from concurrent calls. It must return a callable with the signature `(arg, index) -> result` that resolves each individual call.

On the Svelte side, usage looks identical to a regular query — each component calls it with a single argument:

```svelte
<script>
  import { get_post_likes } from '$lib/posts.remote';
</script>

{#each posts as post}
  <div>
    {#await get_post_likes(post.id) then likes}
      <span>{likes} likes</span>
    {/await}
  </div>
{/each}
```

Even though each iteration calls `get_post_likes` individually, SvelteKit collects all calls that happen within the same render and sends them as a single batched request. Instead of N database queries, you get one.

### Refreshing batch queries

Batch queries support `.refresh()` and `.set()` for individual arguments, both from the client and inside `@command` / `@form` handlers:

```python
@command
async def bump_likes(post_id: int) -> None:
    await db.increment_likes(post_id)
    await get_post_likes(post_id).refresh()  # re-fetches just this post's likes
```

```svelte
<button onclick={() => get_post_likes(post.id).refresh()}>
  Refresh
</button>
```

Each `.refresh()` call re-executes the batch function with just the single argument — it does not refetch all active batch entries.

### When to use batch

Use `@query.batch` when the same query is called many times with different arguments in a single render — lists of cards, rows in a table, items in a feed. If a query is only ever called once at a time, regular `@query` is simpler.

## Accessing the request

Use `get_request_event()` to access cookies and other request data:

```python
from fluidkit import query, error, get_request_event

@query
async def get_profile():
    event = get_request_event()
    session_id = event.cookies.get("session_id")
    if not session_id:
        error(401, "Unauthorized")
    return await db.get_user(session_id)
```

> Queries can read cookies but not set them. To set cookies, use [`@form`](form.md) or [`@command`](command.md).

## Next steps

- **[@form](form.md)** — form handling with file uploads, progressive enhancement, and cache invalidation
- **[@command](command.md)** — write data from anywhere, not tied to a form
- **[@prerender](prerender.md)** — build-time data with optional runtime fallback
