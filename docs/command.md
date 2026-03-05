# @command

Use `@command` to write data from anywhere — event handlers, button clicks, any imperative call. Unlike [`@form`](form.md), commands are not tied to a `<form>` element and require JavaScript.

> Prefer `@form` where possible, since it works without JavaScript via progressive enhancement. Use `@command` when the action doesn't map naturally to a form submission.

## Basic usage

```python
# src/lib/posts.py
from fluidkit import command

@command
async def like_post(post_id: int) -> bool:
    return await db.increment_likes(post_id)
```

Call it from an event handler on the Svelte side:

```svelte
<script>
  import { like_post } from '$lib/posts.remote';

  let { post } = $props();
</script>

<button onclick={async () => {
  try {
    await like_post(post.id);
  } catch (err) {
    showToast('Something went wrong');
  }
}}>
  👍 Like
</button>
```

> Commands cannot be called during render — only from event handlers or other imperative code.

## Arguments and return types

Like all decorators, annotate parameters and return types for full type safety:

```python
from pydantic import BaseModel
from fluidkit import command

class LikeResult(BaseModel):
    post_id: int
    new_count: int

@command
async def like_post(post_id: int) -> LikeResult:
    count = await db.increment_likes(post_id)
    return LikeResult(post_id=post_id, new_count=count)
```

```svelte
<button onclick={async () => {
  const result = await like_post(post.id);
  console.log(result.new_count); // fully typed
}}>
  👍 Like
</button>
```

## Errors

Raise `error()` to return an HTTP error to the client:

```python
from fluidkit import command, error, get_request_event

@command
async def delete_post(post_id: int) -> None:
    event = get_request_event()
    session_id = event.cookies.get("session_id")
    if not session_id:
        raise error(401, "Unauthorized")
    
    post = await db.find(post_id)
    if not post:
        raise error(404, "Not found")
    
    await db.delete(post_id)
```

## Updating queries

After a mutation, you'll usually want to update related queries. There are two approaches — server-driven and client-driven.

### Server-driven

Inside the command handler, call `.refresh()` on any query to re-execute it and send the new data back with the command response in a single round-trip:

```python
from fluidkit import query, command

@query
async def get_posts() -> list[Post]:
    return await db.get_all_posts()

@command
async def like_post(post_id: int) -> None:
    await db.increment_likes(post_id)
    await get_posts().refresh()  # re-runs get_posts, sends result with this response
```

If you already have the updated data, use `.set()` to update the query's value without re-executing it:

```python
@command
async def like_post(post_id: int) -> None:
    updated_posts = await db.increment_and_return_all(post_id)
    await get_posts().set(updated_posts)  # no re-execution, just sets the value
```

Both approaches are single-flight mutations — the updated query data travels back with the command response, avoiding a second network round-trip.

### Client-driven

Alternatively, specify which queries to update from the Svelte side using `.updates()`:

```svelte
<button onclick={async () => {
  await like_post(post.id).updates(get_posts());
}}>
  👍 Like
</button>
```

For optimistic updates, use `.withOverride()` to set a temporary value while the command is in flight:

```svelte
<script>
  import { get_posts, like_post } from '$lib/posts.remote';

  let { post } = $props();
</script>

<button onclick={async () => {
  await like_post(post.id).updates(
    get_posts().withOverride((posts) =>
      posts.map(p => p.id === post.id ? { ...p, likes: p.likes + 1 } : p)
    )
  );
}}>
  👍 {post.likes}
</button>
```

The override is applied immediately and released when the command completes or fails.

## Cookies

Commands can read and set cookies:

```python
from fluidkit import command, get_request_event

@command
async def logout() -> None:
    event = get_request_event()
    event.cookies.set("session_id", "", httponly=True, path="/", max_age=0)
```

## Redirects

Commands do not support redirects. If you raise `Redirect` inside a `@command`, it will be logged as a warning and ignored on the client. Use [`@form`](form.md) if you need redirect behavior after a mutation.

## Next steps

- **[@form](form.md)** — form-based mutations with progressive enhancement and redirects
- **[@query](query.md)** — the queries you'll be updating
- **[@prerender](prerender.md)** — build-time data with optional runtime fallback
