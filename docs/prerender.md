# @prerender

Use `@prerender` to fetch data at build time. Prerendered data is served as static assets from a CDN, making navigation near-instant. Use this for content that changes only when you redeploy.

## Basic usage

```python
# src/lib/content.py
from fluidkit import prerender
from pydantic import BaseModel

class Post(BaseModel):
    slug: str
    title: str
    content: str

@prerender
async def get_posts() -> list[Post]:
    return await db.get_all_posts()
```

```svelte
<script>
  import { get_posts } from '$lib/content.remote';
</script>

{#each await get_posts() as post}
  <a href="/blog/{post.slug}">{post.title}</a>
{/each}
```

On the client, prerendered data is cached using the browser's [Cache API](https://developer.mozilla.org/en-US/docs/Web/API/Cache). This cache survives page reloads and is cleared when the user first visits a new deployment.

## Arguments

Like `@query`, prerender functions can accept arguments:

```python
from fluidkit import prerender, error

@prerender
async def get_post(slug: str) -> Post:
    post = await db.find(slug)
    if not post:
        raise error(404, "Not found")
    return post
```

```svelte
<script>
  import { get_post } from '$lib/content.remote';

  let { params } = $props();
</script>

{#await get_post(params.slug) then post}
  <h1>{post.title}</h1>
  <div>{@html post.content}</div>
{/await}
```

Any calls found by SvelteKit's crawler during prerendering are saved automatically. But you can also specify which values to prerender using the `inputs` option.

## Prerender inputs

Pass a list of arguments to prerender at build time:

```python
@prerender(inputs=["hello-world", "about-fluidkit", "getting-started"])
async def get_post(slug: str) -> Post:
    post = await db.find(slug)
    if not post:
        raise error(404, "Not found")
    return post
```

You can also use a callable that returns the list:

```python
@prerender(inputs=lambda: db.get_all_slugs())
async def get_post(slug: str) -> Post:
    ...
```

> Callable inputs are evaluated at build time but cannot be serialized into the generated `.remote.ts` file. Static lists are preferred when possible.

## Dynamic fallback

By default, prerender functions are excluded from your server bundle — calling them with an argument that wasn't prerendered will fail. Set `dynamic=True` to allow runtime fallback for non-prerendered arguments:

```python
@prerender(inputs=["hello-world", "about-fluidkit"], dynamic=True)
async def get_post(slug: str) -> Post:
    post = await db.find(slug)
    if not post:
        raise error(404, "Not found")
    return post
```

With `dynamic=True`, "hello-world" and "about-fluidkit" are prerendered at build time. Any other slug is fetched from the server at runtime — slower on first load, but the function still works.

## No-argument prerender

For data with no arguments, `@prerender` is used bare with no options:

```python
@prerender
async def get_site_config() -> SiteConfig:
    return await db.get_config()
```

This runs once at build time. Every page that calls `get_site_config()` gets the cached result instantly.

## When to use @prerender vs @query

| | `@prerender` | `@query` |
|---|---|---|
| Data fetched | At build time | At request time |
| Speed | Instant (static asset) | Network round-trip |
| Freshness | Stale until redeployment | Always current |
| Use case | Blog posts, docs, config | User data, dashboards, feeds |

Use `@prerender` with `dynamic=True` for a hybrid approach — prerender known content for speed, fall back to the server for new content.

## Limitations

- Prerender functions cannot set cookies (read-only, same as `@query`)
- Prerender functions do not support `.refresh()` or `.set()` — data is static
- Callable `inputs` work at build time but won't appear in the generated `.remote.ts`

## Next steps

- **[@query](query.md)** — dynamic data fetching at request time
- **[@form](form.md)** — form-based mutations with progressive enhancement
- **[@command](command.md)** — imperative mutations from event handlers
