import logging
from fastapi import Request
from functools import update_wrapper
from fastapi.responses import JSONResponse
from fluidkit.exceptions import HTTPError, Redirect
from typing import Callable, TypeVar, Awaitable, ParamSpec

from fluidkit.models import (
    DecoratorType,
    create_error_response,
    create_query_response,
    create_command_response,
    create_redirect_response,
)
from fluidkit.utilities import (
    extract_metadata,
    parse_request_data,
    build_json_response,
    setup_request_context,
    inject_request_if_needed,
)
from fluidkit.context import (
    FluidKitContext, set_context,
    reset_request_event, reset_context,
)
from fluidkit.types import RemoteProxy
from fluidkit.registry import fluidkit_registry


T = TypeVar('T')
P = ParamSpec('P')
logger = logging.getLogger(__name__)


_FORM_DOC_SUFFIX = """

**Fluidkit Note**: When testing with files in Swagger UI, send complex types as JSON strings.
Example: user: '{"name":"John","email":"john@example.com","age":30}'
"""


# =================================================================================
# Internal helpers
# =================================================================================

def _error_response(e: Exception, status: int = 500, message: str | None = None) -> JSONResponse:
    if status == 500:
        logger.exception(e)
    content = create_error_response(e=e if status == 500 else None, message=message)
    return JSONResponse(
        status_code=status,
        content=content.model_dump(by_alias=True, exclude_none=True),
    )


def _make_remote(
    func: Callable[P, Awaitable[T]],
    decorator_type: DecoratorType,
    *,
    allow_set_cookies: bool = False,
    use_context: bool = False,
    use_form_parsing: bool = False,
    redirect_behavior: str = "none",   # "none" | "respond" | "warn"
    catch_value_error: bool = False,
    handler_doc_suffix: str = "",
):
    """
    Core factory — builds the FastAPI handler, registers the route,
    and returns (wrapper, metadata).

    Behavior matrix:
      query:     context=no,  cookies=ro, body=json, redirect=none,    valuerror=no
      command:   context=yes, cookies=rw, body=json, redirect=warn,    valuerror=no
      form:      context=yes, cookies=rw, body=form, redirect=respond, valuerror=yes
      prerender: context=no,  cookies=ro, body=json, redirect=none,    valuerror=no
    """
    metadata, request_param_name, filtered_params, sig = extract_metadata(
        func=func, decorator_type=decorator_type
    )

    async def fastapi_handler(request: Request):
        request_event, cookies, request_event_token = setup_request_context(
            request=request, allow_set_cookies=allow_set_cookies
        )
        ctx = None
        ctx_token = None
        if use_context:
            ctx = FluidKitContext()
            ctx_token = set_context(ctx)

        try:
            if use_form_parsing:
                body = await parse_request_data(request, sig)
            else:
                body = await request.json()

            kwargs = inject_request_if_needed(
                sig=sig, args=(), kwargs=body,
                request_event=request_event,
                request_param_name=request_param_name,
            )
            result = await func(**kwargs)

            if use_context:
                response_data = create_command_response(result, ctx.mutations)
            else:
                response_data = create_query_response(result)

            return build_json_response(response_data, cookies)

        except Redirect as e:
            if redirect_behavior == "respond":
                response_data = create_redirect_response(e.status, e.location)
                return build_json_response(response_data, cookies)
            if redirect_behavior == "warn":
                logger.warning(
                    "@command '%s' raised Redirect — redirects are not supported in commands "
                    "and will be ignored on the client. Use @form if redirect behavior is needed.",
                    func.__name__,
                )
                response_data = create_command_response(None, ctx.mutations)
                return build_json_response(response_data, cookies)
            # no redirect handling → falls through as unhandled exception
            return _error_response(e)

        except HTTPError as e:
            return JSONResponse(
                status_code=e.status,
                content=create_error_response(message=e.message)
                    .model_dump(by_alias=True, exclude_none=True),
            )

        except ValueError as e:
            if catch_value_error:
                return _error_response(
                    e, status=400,
                    message=f"Invalid data in {func.__name__}(): {e}",
                )
            return _error_response(e)

        except Exception as e:
            return _error_response(e)

        finally:
            if ctx_token is not None:
                reset_context(ctx_token)
            reset_request_event(request_event_token)

    fastapi_handler.__name__ = func.__name__
    if handler_doc_suffix:
        fastapi_handler.__doc__ = f"{func.__doc__ or ''}{handler_doc_suffix}"
    else:
        fastapi_handler.__doc__ = func.__doc__

    fluidkit_registry.register(metadata, fastapi_handler)

    def wrapper(*args: P.args, **kwargs: P.kwargs) -> RemoteProxy[T]:
        return RemoteProxy(
            sig=sig, args=args, kwargs=kwargs,
            executor=func,
            func_name=f"{metadata.module}#{metadata.name}",
        )

    update_wrapper(wrapper, func)
    return wrapper, metadata


# =================================================================================
# Public decorators
# =================================================================================

def query(func: Callable[P, Awaitable[T]]) -> Callable[P, RemoteProxy[T]]:
    """
    Create a remote query function for reading data.

    Queries are read-only operations that can be called from SvelteKit components.
    They support caching and can be refreshed on demand.

    Example:
```python
        @query
        async def get_user(user_id: str) -> User:
            return await db.get_user(user_id)

        # In SvelteKit:
        # const user = await getUser('123');
        # await getUser('123').refresh();
```
    """
    wrapper, _ = _make_remote(func, DecoratorType.QUERY)
    return wrapper


def command(func: Callable[P, Awaitable[T]]) -> Callable[P, RemoteProxy[T]]:
    """
    Create a remote command function for mutations.

    Commands perform write operations and can update query caches in a single
    request using .refresh() or .set() within the function body.

    Example:
```python
        @command
        async def add_like(post_id: str) -> None:
            await db.increment_likes(post_id)
            await get_posts().refresh()  # Update client cache

        # In SvelteKit:
        # await addLike('post-123');
```
    """
    wrapper, _ = _make_remote(
        func, DecoratorType.COMMAND,
        allow_set_cookies=True,
        use_context=True,
        redirect_behavior="warn",
    )
    return wrapper


def form(func: Callable[P, Awaitable[T]]) -> Callable[P, RemoteProxy[T]]:
    """
    Create a remote form handler with progressive enhancement.

    Forms work without JavaScript and support file uploads. Complex types
    should be sent as JSON strings when using multipart/form-data.

    Example:
```python
        @form
        async def create_post(title: str, photo: FileUpload) -> None:
            await storage.save(photo.filename, await photo.read())
            await db.insert(title)
            raise Redirect(303, '/posts')

        # In SvelteKit:
        # <form {...createPost}>
        #   <input {...createPost.fields.title.as('text')} />
        #   <input {...createPost.fields.photo.as('file')} />
        # </form>
```
    """
    wrapper, _ = _make_remote(
        func, DecoratorType.FORM,
        allow_set_cookies=True,
        use_context=True,
        use_form_parsing=True,
        redirect_behavior="respond",
        catch_value_error=True,
        handler_doc_suffix=_FORM_DOC_SUFFIX,
    )
    return wrapper


def prerender(func=None, *, inputs=None, dynamic=False):
    """
    Create a remote function that prerenders data at build time.

    Args:
        inputs: List of input values or callable returning list. Used at build
                time to determine which function calls to cache.
        dynamic: If True, allows runtime calls with non-prerendered arguments.

    Example:
```python
        @prerender
        async def get_posts() -> list[Post]:
            return await db.get_posts()

        @prerender(inputs=['post-1', 'post-2'])
        async def get_post(slug: str) -> Post:
            return await db.get_post(slug)

        @prerender(inputs=lambda: db.get_all_slugs(), dynamic=True)
        async def get_dynamic_post(slug: str) -> Post:
            return await db.get_post(slug)
```
    """
    def decorator(fn: Callable[P, Awaitable[T]]) -> Callable[P, RemoteProxy[T]]:
        wrapper, metadata = _make_remote(fn, DecoratorType.PRERENDER)
        metadata.prerender_inputs = inputs
        metadata.prerender_dynamic = dynamic
        return wrapper

    if func is None:
        return decorator
    return decorator(func)
    