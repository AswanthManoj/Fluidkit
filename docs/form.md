# @form

Use `@form` to write data via `<form>` elements. Forms work without JavaScript (progressive enhancement), support file uploads, and can trigger redirects.

## Basic usage
```python
# src/lib/posts.py
from fluidkit import form

@form
async def add_post(title: str, content: str) -> None:
    await db.insert(title, content)
```

The returned object spreads onto a `<form>` element. Field names match your Python parameter names:
```svelte
<script>
  import { add_post } from '$lib/posts.remote';
</script>

<form {...add_post}>
  <input {...add_post.fields.title.as('text')} placeholder="Title" />
  <textarea {...add_post.fields.content.as('text')} placeholder="Content"></textarea>
  <button>Publish</button>
</form>
```

The form works as a native HTML form submission if JavaScript is unavailable. When JavaScript is present, SvelteKit progressively enhances it to submit without a full page reload.

## Fields

Each parameter in your function becomes a field. Call `.as(...)` on a field to get the attributes for the corresponding input type:
```python
@form
async def create_profile(name: str, age: int, bio: str) -> None:
    ...
```
```svelte
<form {...create_profile}>
  <input {...create_profile.fields.name.as('text')} />
  <input {...create_profile.fields.age.as('number')} />
  <textarea {...create_profile.fields.bio.as('text')}></textarea>
  <button>Save</button>
</form>
```

The `.as(...)` method sets the correct input type, the `name` attribute used to construct form data, and the `aria-invalid` state for validation.

## File uploads

Use `FileUpload` for file parameters. On the Svelte side, this maps to a file input:
```python
from fluidkit import form, FileUpload

@form
async def upload_avatar(username: str, photo: FileUpload) -> None:
    contents = await photo.read()
    await storage.save(photo.filename, contents)
    await db.update_avatar(username, photo.filename)
```
```svelte
<form {...upload_avatar} enctype="multipart/form-data">
  <input {...upload_avatar.fields.username.as('text')} />
  <input {...upload_avatar.fields.photo.as('file')} />
  <button>Upload</button>
</form>
```

Add `enctype="multipart/form-data"` to the form when using file inputs. `FileUpload` extends FastAPI's `UploadFile`, so all its methods (`read()`, `filename`, `content_type`, etc.) are available.

## Redirects

Raise `Redirect` to navigate after a successful submission:
```python
from fluidkit import form, Redirect

@form
async def create_post(title: str, content: str) -> None:
    slug = title.lower().replace(" ", "-")
    await db.insert(slug, title, content)
    raise Redirect(303, f"/blog/{slug}")
```

The redirect is captured by the FluidKit backend and forwarded to SvelteKit, which performs the navigation on the client. Common status codes:

- `303` — See Other (most common for form submissions, redirects as GET)
- `307` — Temporary Redirect (preserves request method)
- `308` — Permanent Redirect (preserves request method, SEO transfers)

## Errors

Raise `error()` to return an HTTP error:
```python
from fluidkit import form, error, get_request_event

@form
async def create_post(title: str, content: str) -> None:
    event = get_request_event()
    session_id = event.cookies.get("session_id")
    if not session_id:
        raise error(401, "Unauthorized")
    await db.insert(title, content)
```

If an error occurs during form submission, the nearest `+error.svelte` page will be rendered. This is different from [`@query`](query.md) (which triggers [`<svelte:boundary>`](https://svelte.dev/docs/svelte/svelte-boundary)) and [`@command`](command.md) (which relies on your own `try/catch`).

## Validation

SvelteKit provides client-side validation via the `issues()` method on each field and the `validate()` method on the form:
```svelte
<form {...add_post} oninput={() => add_post.validate()}>
  <label>
    Title
    {#each add_post.fields.title.issues() as issue}
      <p class="error">{issue.message}</p>
    {/each}
    <input {...add_post.fields.title.as('text')} />
  </label>

  <button>Publish</button>
</form>
```

Server-side validation comes from Python's type system — if a parameter can't be coerced to the expected type (e.g. a string sent for an `int` field), the form handler returns a 400 error automatically.

## Returns

Instead of redirecting, a form can return data. The result is available on the form object:
```python
@form
async def add_post(title: str, content: str) -> dict:
    await db.insert(title, content)
    return {"success": True}
```
```svelte
<form {...add_post}>
  <!-- fields -->
  <button>Publish</button>
</form>

{#if add_post.result?.success}
  <p>Published!</p>
{/if}
```

This value is ephemeral — it vanishes on resubmit, navigation, or page reload.

## Single-flight mutations

By default, all queries on the page are refreshed after a successful form submission. For more control, you can specify which queries to update inside the form handler. This avoids a second round-trip — the updated data is sent back with the form response.

Use `.refresh()` to re-execute a query and include its new result:
```python
from fluidkit import form, query

@query
async def get_posts() -> list[Post]:
    return await db.get_all_posts()

@form
async def add_post(title: str, content: str) -> None:
    await db.insert(title, content)
    await get_posts().refresh()  # re-runs get_posts, sends result with this response
```

Use `.set()` to update a query's value directly without re-executing it — useful when you already have the new data:
```python
@form
async def add_post(title: str, content: str) -> None:
    new_post = await db.insert_and_return(title, content)
    all_posts = await db.get_all_posts()
    await get_posts().set(all_posts)  # set value without re-running the query
```

Both `.refresh()` and `.set()` only work inside `@form` and `@command` handlers. Calling them elsewhere produces a warning.

## Cookies

Forms can read and set cookies:
```python
from fluidkit import form, get_request_event

@form
async def login(username: str, _password: str) -> None:
    user = await db.authenticate(username, _password)
    event = get_request_event()
    event.cookies.set("session_id", user.session, httponly=True, path="/")
```

> Prefix sensitive parameter names with an underscore (e.g. `_password`) to prevent them from being sent back to the client on validation failure — matching SvelteKit's convention.

## Enhance

Customize submission behavior with the `enhance` method on the Svelte side:
```svelte
<form {...add_post.enhance(async ({ form, data, submit }) => {
  try {
    await submit();
    form.reset();
    showToast('Published!');
  } catch (error) {
    showToast('Something went wrong');
  }
})}>
  <!-- fields -->
</form>
```

When using `enhance`, the form is not automatically reset — call `form.reset()` explicitly if needed.

## Supported parameter types

`@form` parameters must be types that can be represented as form fields:

- `str`, `int`, `float`, `bool` — primitive inputs
- `FileUpload` — file inputs
- `list[str]`, `list[int]`, etc. — multiple inputs with the same field name
- `Optional[...]` — optional fields

For complex nested types (Pydantic models, dicts, unions), use [`@command`](command.md) instead. This is a FluidKit-specific constraint — SvelteKit's native forms support nested objects and arrays, but FluidKit's codegen currently limits forms to flat field structures.

## Next steps

- **[@command](command.md)** — write data from event handlers, not tied to a form
- **[@query](query.md)** — read data, the queries you'll be refreshing
- **[@prerender](prerender.md)** — build-time data with optional runtime fallback
