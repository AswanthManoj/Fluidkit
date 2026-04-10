# Getting Started

## Installation

```bash
pip install fluidkit
```

No system Node.js required — FluidKit bundles it automatically.

## Create a project

```bash
fluidkit init my-app
cd my-app
```

This scaffolds a SvelteKit project with FluidKit wired in and a working demo app:

```
my-app/
├── src/
│   ├── routes/
│   │   ├── +layout.svelte
│   │   └── +page.svelte
│   ├── lib/
│   │   ├── demo.py              # backend logic
│   │   └── demo.remote.ts       # generated — don't edit
│   └── app.py                   # FastAPI entry point
├── fluidkit.config.json
├── svelte.config.js
└── package.json
```

## Run it

```bash
fluidkit dev
```

This starts both the FastAPI backend and Vite dev server together with hot module reloading. Open the app and you'll see a working posts demo — try adding posts and liking them.

## How the demo works

The scaffolded `demo.py` contains three decorated functions:

```python
# src/lib/demo.py
from fluidkit import query, command, form

db = {
    "posts": [
        {"id": 1, "title": "Hello World", "content": "This is the first post.", "likes": 10},
        {"id": 2, "title": "Fluidkit", "content": "Fluidkit is awesome!", "likes": 50},
        {"id": 3, "title": "Python and Svelte", "content": "Using Python with Svelte is great!", "likes": 25},
    ]
}

@query
async def get_posts():
    return db["posts"]

@command
async def like_post(post_id: int):
    for post in db["posts"]:
        if post["id"] == post_id:
            post["likes"] += 1
            await get_posts().refresh()
            return True
    return None

@form
async def add_post(title: str, content: str):
    new_post = {
        "id": len(db["posts"]) + 1,
        "title": title,
        "content": content,
        "likes": 0,
    }
    db["posts"].append(new_post)
    await get_posts().refresh()
```

The route imports and uses them directly:

```svelte
<!-- src/routes/+page.svelte -->
<script>
  import { get_posts, like_post, add_post } from '$lib/demo.remote';
</script>

<h1>Posts</h1>

<form {...add_post}>
  <input {...add_post.fields.title.as('text')} placeholder="Title" />
  <input {...add_post.fields.content.as('text')} placeholder="Content" />
  <button>Add Post</button>
</form>

{#each await get_posts() as post}
  <div>
    <h2>{post.title}</h2>
    <p>{post.content}</p>
    <button onclick={async () => await like_post(post.id)}>
      👍 {post.likes}
    </button>
  </div>
{/each}
```

Notice the import path: `$lib/demo.remote`. FluidKit generates `demo.remote.ts` next to your `demo.py` — this is a standard SvelteKit [remote function](https://svelte.dev/docs/kit/remote-functions) file that proxies calls to your Python backend. You never need to edit it.

Edit `demo.py`, save, and changes reflect immediately. Try modifying the data, adding new decorated functions, or changing parameter types — the generated `.remote.ts` updates automatically.

## What just happened?

When you decorated functions with `@query`, `@command`, and `@form`, FluidKit:

1. **Registered each function as a FastAPI endpoint** — with parameter types, validation, and return types extracted automatically
2. **Generated a `.remote.ts` file** — a SvelteKit remote function wrapper that calls your FastAPI endpoint with full type safety
3. **Wired up cache invalidation** — `await get_posts().refresh()` inside `like_post` and `add_post` tells SvelteKit to refetch that query in the same round-trip (single-flight mutation)

The Svelte side works exactly like native SvelteKit remote functions — `await` in templates, form spreading, field helpers — because that's exactly what the generated code is.

All four decorators support both `async` and regular sync functions. Use `async def` when you need `await` — for database calls, HTTP requests, or `.refresh()` and `.set()`. Use plain `def` for simple synchronous logic. FluidKit handles both transparently.

## Next steps

- **[@query](query.md)** — arguments, validation, refresh
- **[@command](command.md)** — writing data, updating queries, optimistic updates
- **[@form](form.md)** — fields, validation, file uploads, progressive enhancement
- **[@prerender](prerender.md)** — build-time data with optional runtime fallback
- **[Hooks](hooks.md)** — lifecycle, request middleware, error handling
- **[Cookbook](cookbook.md)** — complete production patterns including auth
- **[CLI](cli.md)** — all available commands
- **[Configuration](config.md)** — `fluidkit.config.json` reference
