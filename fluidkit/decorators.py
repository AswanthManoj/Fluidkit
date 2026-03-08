import logging
from collections.abc import Awaitable, Callable
from functools import update_wrapper
from typing import ParamSpec, TypeVar

from fastapi import Request
from fastapi.responses import JSONResponse

from fluidkit.context import (
    FluidKitContext,
    reset_context,
    reset_request_event,
    set_context,
)
from fluidkit.exceptions import HTTPError, Redirect
from fluidkit.models import (
    DecoratorType,
    create_batch_query_response,
    create_command_response,
    create_error_response,
    create_query_response,
    create_redirect_response,
)
from fluidkit.registry import fluidkit_registry
from fluidkit.types import RemoteProxy
from fluidkit.utilities import (
    build_json_response,
    extract_metadata,
    inject_request_if_needed,
    parse_request_data,
    setup_request_context,
)

T = TypeVar("T")
P = ParamSpec("P")
logger = logging.getLogger(__name__)


# =================================================================================
# Internal helpers
# =================================================================================


def _error_response(e: Exception, status: int = 500, message: str | None = None) -> JSONResponse:
    if status == 500:
        logger.exception(e)
    content = create_error_response(
        e=e if status == 500 else None,
        message=message,
        dev=fluidkit_registry.dev,
    )
    return JSONResponse(
        status_code=status,
        content=content.model_dump(by_alias=True, exclude_none=True),
    )


def _http_error_response(e: HTTPError) -> JSONResponse:
    return JSONResponse(
        status_code=e.status,
        content=create_error_response(message=e.message, dev=fluidkit_registry.dev).model_dump(
            by_alias=True, exclude_none=True
        ),
    )


def _wrap_and_register(func, metadata, sig):
    """Create the RemoteProxy wrapper. Shared by all decorators."""

    def wrapper(*args: P.args, **kwargs: P.kwargs) -> RemoteProxy[T]:
        return RemoteProxy(
            sig=sig,
            args=args,
            kwargs=kwargs,
            executor=func,
            func_name=f"{metadata.module}#{metadata.name}",
        )

    update_wrapper(wrapper, func)
    return wrapper


def _make_remote(
    func: Callable[P, Awaitable[T]],
    decorator_type: DecoratorType,
    *,
    allow_set_cookies: bool = False,
    use_context: bool = False,
    use_form_parsing: bool = False,
    redirect_behavior: str = "none",
    catch_value_error: bool = False,
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
    metadata, request_param_name, sig = extract_metadata(func=func, decorator_type=decorator_type)

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
                sig=sig,
                args=(),
                kwargs=body,
                request_event=request_event,
                request_param_name=request_param_name,
            )
            result = await func(**kwargs)

            if use_context:
                response_data = create_command_response(result, ctx.mutations, cookies.serialize())
            else:
                response_data = create_query_response(result)

            return build_json_response(response_data)

        except Redirect as e:
            if redirect_behavior == "respond":
                response_data = create_redirect_response(e.status, e.location, cookies.serialize())
                return build_json_response(response_data)
            if redirect_behavior == "warn":
                logger.warning(
                    "@command '%s' raised Redirect — redirects are not supported in commands "
                    "and will be ignored on the client. Use @form if redirect behavior is needed.",
                    func.__name__,
                )
                response_data = create_command_response(None, ctx.mutations, cookies.serialize())
                return build_json_response(response_data)
            return _error_response(e)

        except HTTPError as e:
            return _http_error_response(e)

        except ValueError as e:
            if catch_value_error:
                return _error_response(
                    e,
                    status=400,
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
    fastapi_handler.__doc__ = func.__doc__

    fluidkit_registry.register(metadata, fastapi_handler)

    wrapper = _wrap_and_register(func, metadata, sig)
    return wrapper, metadata


# =================================================================================
# Public decorators
# =================================================================================


class query:
    """
    Create a remote query function for reading data.

    Queries are read-only operations that can be called from SvelteKit components.
    They support caching and can be refreshed on demand.

    Example:
    ```python
        @query
        async def get_user(user_id: str) -> User:
            return await db.get_user(user_id)
    ```
    """

    def __new__(cls, func: Callable[P, Awaitable[T]]) -> Callable[P, RemoteProxy[T]]:
        wrapper, _ = _make_remote(func, DecoratorType.QUERY)
        return wrapper

    @staticmethod
    def batch(func: Callable[P, Awaitable[T]]) -> Callable[P, RemoteProxy[T]]:
        """
        Create a batched remote query function.

        Batches concurrent calls into a single request. The decorated function
        receives a list of all arguments and must return a callable that
        resolves each individual call.

        Example:
        ```python
            @query.batch
            async def get_weather(city_ids: list[str]):
                weather = await db.get_bulk(city_ids)
                lookup = {w.city_id: w for w in weather}
                return lambda city_id: lookup.get(city_id)
        ```
        """

        metadata, request_param_name, sig = extract_metadata(func=func, decorator_type=DecoratorType.QUERY_BATCH)

        async def fastapi_handler(request: Request):
            request_event, cookies, request_event_token = setup_request_context(
                request=request, allow_set_cookies=False
            )

            try:
                body = await request.json()
                args_list = body.get("args", [])
                result = await func(args_list)

                if not callable(result):
                    param_name = metadata.parameters[0].name if metadata.parameters else "items"
                    raise TypeError(
                        f"@query.batch '{func.__name__}' must return a callable, "
                        f"got {type(result).__name__}. Expected pattern:\n\n"
                        f"  @query.batch\n"
                        f"  async def {func.__name__}({param_name}: list[...]):\n"
                        f"      ...\n"
                        f"      return lambda item: result_for(item)\n"
                    )

                results = [result(arg, i) for i, arg in enumerate(args_list)]
                response_data = create_batch_query_response(results)
                return build_json_response(response_data)

            except HTTPError as e:
                return _http_error_response(e)

            except Exception as e:
                return _error_response(e)

            finally:
                reset_request_event(request_event_token)

        fastapi_handler.__name__ = func.__name__
        fastapi_handler.__doc__ = func.__doc__

        async def _single_executor(**kwargs):
            """Wrap batch function for single-item calls (refresh/set)."""
            single_arg = next(iter(kwargs.values()))
            resolver = await func([single_arg])
            return resolver(single_arg, 0)

        update_wrapper(_single_executor, func)

        fluidkit_registry.register(metadata, fastapi_handler)
        return _wrap_and_register(_single_executor, metadata, sig)


class command:
    """
    Create a remote command function for mutations.

    Commands perform write operations and can update query caches in a single
    request using .refresh() or .set() within the function body.

    Example:
    ```python
        @command
        async def add_like(post_id: str) -> None:
            await db.increment_likes(post_id)
            await get_posts().refresh()
    ```
    """

    def __new__(cls, func: Callable[P, Awaitable[T]]) -> Callable[P, RemoteProxy[T]]:

        wrapper, _ = _make_remote(
            func,
            DecoratorType.COMMAND,
            allow_set_cookies=True,
            use_context=True,
            redirect_behavior="warn",
        )
        return wrapper


class form:
    """
    Create a remote form handler with progressive enhancement.

    Forms work without JavaScript and support file uploads, nested
    Pydantic models, and complex types natively.

    Example:
    ```python
        @form
        async def create_post(title: str, photo: FileUpload) -> None:
            await storage.save(photo.filename, await photo.read())
            raise Redirect(303, '/posts')
    ```
    """

    def __new__(cls, func: Callable[P, Awaitable[T]]) -> Callable[P, RemoteProxy[T]]:
        wrapper, _ = _make_remote(
            func,
            DecoratorType.FORM,
            allow_set_cookies=True,
            use_context=True,
            use_form_parsing=True,
            redirect_behavior="respond",
            catch_value_error=True,
        )
        return wrapper


class prerender:
    """
    Create a remote function that prerenders data at build time.

    Args:
        inputs: List of input values or callable returning list.
        dynamic: If True, allows runtime calls with non-prerendered arguments.

    Example:
    ```python
        @prerender
        async def get_posts() -> list[Post]:
            return await db.get_posts()

        @prerender(inputs=['post-1', 'post-2'], dynamic=True)
        async def get_post(slug: str) -> Post:
            return await db.get_post(slug)
    ```
    """

    def __new__(cls, func=None, *, inputs=None, dynamic=False):
        def decorator(fn: Callable[P, Awaitable[T]]) -> Callable[P, RemoteProxy[T]]:
            wrapper, metadata = _make_remote(fn, decorator_type=DecoratorType.PRERENDER)
            metadata.prerender_inputs = inputs
            metadata.prerender_dynamic = dynamic
            return wrapper

        if func is None:
            return decorator
        return decorator(func)
