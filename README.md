# FluidKit

<div align="center">
  <img src="https://azure-deliberate-dog-514.mypinata.cloud/ipfs/bafkreiay74jzankyzj2zh4zemmpidafbsrcr4hwjxnl5e3qk32xyi6t3hi" alt="FluidKit Logo" width="125">
</div>

<div align="center">
  <strong>Web development for the Pythonist</strong>
</div>

<br/>

FluidKit bridges Python and SvelteKit into a unified fullstack framework. Write backend functions in Python — FluidKit registers them as FastAPI endpoints and wraps them in SvelteKit-native remote functions with full type safety, cookie forwarding, file uploads, redirects, and single-flight cache invalidation.

```bash
pip install fluidkit
```



## How it works

Decorate Python functions. FluidKit registers them as FastAPI endpoints internally and generates colocated `.remote.ts` files that SvelteKit imports as [remote functions](https://svelte.dev/docs/kit/remote-functions) directly.

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

            # invalidates client cache in the same request with single flight mutations
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

    await get_posts().refresh() # invalidates client cache in the same request with single flight mutations
```

```svelte
<!-- src/routes/+page.svelte -->
<script>
    import { get_posts, like_post, add_post } from '$lib/demo.remote';
</script>

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

No manual fetch calls. No duplicated types. No glue code.

<details>
<summary><b>🤫 how does this work?</b></summary>
FluidKit reflects on your decorated functions at import time — inspecting parameters, return types, and Pydantic models — and generates colocated `.remote.ts` files wrapping each function in a SvelteKit-native `query`, `command`, `form`, or `prerender` remote function call. In dev mode this re-runs on every save via HMR. The generated files are real TypeScript you can inspect, import, and version control.
</details>



## Decorators

| Decorator | Use case | SvelteKit docs |
|---|---|---|
| `@query` | Read data — cached, refreshable | [query](https://svelte.dev/docs/kit/remote-functions#query) |
| `@command` | Write data — single-flight cache invalidation | [command](https://svelte.dev/docs/kit/remote-functions#command) |
| `@form` | Form actions — file uploads, progressive enhancement, redirects | [form](https://svelte.dev/docs/kit/remote-functions#form) |
| `@prerender` | Build-time data fetching with optional runtime fallback | [prerender](https://svelte.dev/docs/kit/remote-functions#prerender) |


## Documentation

- [Getting Started](docs/quickstart.md)
- [Remote Functions](docs/remote_functions.md) — query, form, command, prerender
- [CLI](docs/cli.md)
- [Configuration](docs/config.md)
- [Examples](docs/examples.md)


## CLI

```bash
fluidkit init                # scaffold SvelteKit project with FluidKit wired in
fluidkit dev                 # run FastAPI + Vite together with HMR
fluidkit build               # codegen + npm run build
fluidkit preview             # preview production build locally
```

No system Node.js required — FluidKit uses `nodejs-wheel` for all Node operations. npm, npx, and node are available through the CLI:

```bash
fluidkit install tailwindcss          # shorthand for npm install
fluidkit install -D prettier          # install as dev dependency
fluidkit npm run build                # any npm command
fluidkit npx sv add tailwindcss       # any npx command
fluidkit node scripts/seed.js         # run node directly
```



## Project config

```json
// fluidkit.config.json
{
  "entry": "src/app.py",
  "host": "0.0.0.0",
  "backend_port": 8000,
  "frontend_port": 5173,
  "schema_output": "src/lib/fluidkit",
  "watch_pattern": "src/**/*.py"
}
```

> NOTE: Flags override config. Config overrides defaults.



## Built with

- [SvelteKit](https://svelte.dev/docs/kit) — frontend framework with remote functions
- [FastAPI](https://fastapi.tiangolo.com/) — API layer and request handling
- [Pydantic](https://docs.pydantic.dev/) — type extraction and validation
- [Jurigged](https://github.com/breuleux/jurigged) — hot module reloading in dev mode
- [nodejs-wheel](https://github.com/nicolo-ribaudo/nodejs-wheel) — bundled Node.js, no system install needed
