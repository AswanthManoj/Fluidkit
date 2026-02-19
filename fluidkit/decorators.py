from http import cookies
import logging
from fastapi import Request
from functools import update_wrapper
from fastapi.responses import JSONResponse
from typing import Callable, TypeVar, Awaitable, ParamSpec

from fluidkit import fluidkit_registry
from fluidkit.exceptions import HTTPError, Redirect
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
    inject_request_if_needed
)
from fluidkit.context import (
    FluidKitContext, set_context,
    reset_request_event, reset_context
)
from fluidkit.types import RemoteProxy
from fluidkit.registry import fluidkit_registry


T = TypeVar('T')
P = ParamSpec('P')
logger = logging.getLogger(__name__)


# =================================================================================
# Remote function decorators
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
    metadata, request_param_name, filtered_params, sig = extract_metadata(
        func=func, 
        decorator_type=DecoratorType.QUERY
    )

    async def fastapi_handler(request: Request):
        request_event, cookies, request_event_token = setup_request_context(
            request=request, 
            allow_set_cookies=False
        )

        try:
            body = await request.json()

            kwargs = inject_request_if_needed(
                sig=sig,
                args=(),
                kwargs=body,
                request_event=request_event,
                request_param_name=request_param_name
            )
                        
            result = await func(**kwargs)
            response_data = create_query_response(result)

            return build_json_response(response_data, cookies)
        except HTTPError as e:
            return JSONResponse(
                status_code=e.status,
                content=create_error_response(message=e.message).model_dump(by_alias=True, exclude_none=True)
            )
        except Exception as e:
            logger.exception(e)
            return JSONResponse(
                status_code=500,
                content=create_error_response(e).model_dump(by_alias=True, exclude_none=True)
            )
        
        finally:
            reset_request_event(request_event_token)

    
    fastapi_handler.__name__ = func.__name__
    fastapi_handler.__doc__ = func.__doc__
    # fastapi_handler.__signature__ = sig.replace(parameters=filtered_params)
    
    fluidkit_registry.register(metadata, fastapi_handler)

    def wrapper(*args: P.args, **kwargs: P.kwargs) -> RemoteProxy[T]:
        return RemoteProxy(
            sig=sig,
            args=args, 
            kwargs=kwargs,
            executor=func, 
            func_name=f"{metadata.module}#{metadata.name}"
        )
    
    update_wrapper(wrapper, func)
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
    metadata, request_param_name, filtered_params, sig = extract_metadata(
        func=func, 
        decorator_type=DecoratorType.COMMAND
    )

    async def fastapi_handler(request: Request):
        request_event, cookies, request_event_token = setup_request_context(
            request=request, 
            allow_set_cookies=True
        )

        ctx = FluidKitContext()
        ctx_token = set_context(ctx)

        try:
            body = await request.json()

            kwargs = inject_request_if_needed(
                sig=sig,
                args=(),
                kwargs=body,
                request_event=request_event,
                request_param_name=request_param_name
            )

            result = await func(**kwargs)

            response_data = create_command_response(result, ctx.mutations)

            return build_json_response(response_data, cookies)
        except Redirect as e:
            logger.warning(
                "@command '%s' raised Redirect — redirects are not supported in commands "
                "and will be ignored on the client. Use @form if redirect behavior is needed.",
                func.__name__
            )
            response_data = create_command_response(None, ctx.mutations)
            return build_json_response(response_data, cookies)
        except HTTPError as e:
            return JSONResponse(
                status_code=e.status,
                content=create_error_response(message=e.message).model_dump(by_alias=True, exclude_none=True)
            )
        except Exception as e:
            logger.exception(e)
            return JSONResponse(
                status_code=500,
                content=create_error_response(e).model_dump(by_alias=True, exclude_none=True)
            )
        
        finally:
            reset_context(ctx_token)
            reset_request_event(request_event_token)

    
    fastapi_handler.__name__ = func.__name__
    fastapi_handler.__doc__ = func.__doc__
    # fastapi_handler.__signature__ = sig.replace(parameters=filtered_params)
    
    fluidkit_registry.register(metadata, fastapi_handler)

    def wrapper(*args: P.args, **kwargs: P.kwargs) -> RemoteProxy[T]:
        return RemoteProxy(
            sig=sig,
            args=args, 
            kwargs=kwargs,
            executor=func, 
            func_name=f"{metadata.module}#{metadata.name}"
        )
    
    update_wrapper(wrapper, func)
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
    metadata, request_param_name, filtered_params, sig = extract_metadata(
        func=func, 
        decorator_type=DecoratorType.FORM
    )

    async def fastapi_handler(request: Request):
        request_event, cookies, request_event_token = setup_request_context(
            request=request, 
            allow_set_cookies=True
        )

        ctx = FluidKitContext()
        ctx_token = set_context(ctx)

        try:
            parsed_data = await parse_request_data(request, sig)

            kwargs = inject_request_if_needed(
                sig=sig,
                args=(),
                kwargs=parsed_data,
                request_event=request_event,
                request_param_name=request_param_name
            )

            result = await func(**kwargs)

            response_data = create_command_response(result, ctx.mutations)

            return build_json_response(response_data, cookies)

        except Redirect as e:
            response_data = create_redirect_response(
                status=e.status,
                location=e.location
            )
            return build_json_response(response_data, cookies)

        except HTTPError as e:
            return JSONResponse(
                status_code=e.status,
                content=create_error_response(message=e.message).model_dump(by_alias=True, exclude_none=True)
            )
        except ValueError as e:
            return JSONResponse(
                status_code=400,
                content=create_error_response(message=f"Invalid data in {func.__name__}(): {str(e)}").model_dump(by_alias=True, exclude_none=True)
            )
        except Exception as e:
            logger.exception(e)
            return JSONResponse(
                status_code=500,
                content=create_error_response(e).model_dump(by_alias=True, exclude_none=True)
            )

        finally:
            reset_context(ctx_token)
            reset_request_event(request_event_token)

    fastapi_handler.__name__ = func.__name__
    fastapi_handler.__doc__ = f"""{func.__doc__ or ''}

**Fluidkit Note**: When testing with files in Swagger UI, send complex types as JSON strings.
Example: user: '{{"name":"John","email":"john@example.com","age":30}}'
"""
    # TODO: Fix signature issue in swagger
    # fastapi_handler.__signature__ = sig.replace(parameters=filtered_params)

    fluidkit_registry.register(metadata, fastapi_handler)

    def wrapper(*args: P.args, **kwargs: P.kwargs) -> RemoteProxy[T]:
        return RemoteProxy(
            sig=sig,
            args=args, 
            kwargs=kwargs,
            executor=func, 
            func_name=f"{metadata.module}#{metadata.name}"
        )

    update_wrapper(wrapper, func)
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
    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, RemoteProxy[T]]:
        metadata, request_param_name, filtered_params, sig = extract_metadata(
            func=func, 
            decorator_type=DecoratorType.PRERENDER
        )
        
        # Add prerender-specific metadata
        metadata.prerender_inputs = inputs
        metadata.prerender_dynamic = dynamic

        async def fastapi_handler(request: Request):
            request_event, cookies, request_event_token = setup_request_context(
                request=request, 
                allow_set_cookies=False  # Can't set cookies in prerender
            )

            try:
                body = await request.json()

                kwargs = inject_request_if_needed(
                    sig=sig,
                    args=(),
                    kwargs=body,
                    request_event=request_event,
                    request_param_name=request_param_name
                )

                result = await func(**kwargs)
                response_data = create_query_response(result)

                return build_json_response(response_data, cookies)
                
            except HTTPError as e:
                return JSONResponse(
                    status_code=e.status,
                    content=create_error_response(message=e.message).model_dump(by_alias=True, exclude_none=True)
                )
            except Exception as e:
                logger.exception(e)
                return JSONResponse(
                    status_code=500,
                    content=create_error_response(e).model_dump(by_alias=True, exclude_none=True)
                )
            
            finally:
                reset_request_event(request_event_token)
        
        fastapi_handler.__name__ = func.__name__
        fastapi_handler.__doc__ = func.__doc__
        # fastapi_handler.__signature__ = sig.replace(parameters=filtered_params)
        
        fluidkit_registry.register(metadata, fastapi_handler)

        def wrapper(*args: P.args, **kwargs: P.kwargs) -> RemoteProxy[T]:
            return RemoteProxy(
                sig=sig,
                args=args, 
                kwargs=kwargs,
                executor=func, 
                func_name=f"{metadata.module}#{metadata.name}"
            )
        
        update_wrapper(wrapper, func)
        return wrapper
    
    if func is None:
        return decorator
    else:
        return decorator(func)
