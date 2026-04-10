class HTTPError(Exception):
    """
    Raise to return an HTTP error response.
    Mirrors SvelteKit's error() function.

    Example:
        ```python
        raise error(404, 'Not found')
        raise error(401, 'Unauthorized')
        ```
    """

    def __init__(self, status: int, message: str):
        if not (400 <= status < 600):
            raise ValueError(f"Status must be 400-599, got {status}")

        self.status = status
        self.message = message
        super().__init__(f"HTTP {status}: {message}")


class Redirect(Exception):
    """
    Raise to trigger a navigation redirect.

    Args:
        status: HTTP redirect status code (300-308)
        location: Destination URL or path

    Example:
        ```python
        @form
        async def create_post(title: str) -> None:
            post_id = await db.insert(title)
            raise Redirect(303, f'/posts/{post_id}')
        ```
    """

    def __init__(self, status: int, location: str):
        if not (300 <= status <= 308):
            raise ValueError(f"Redirect status must be 300-308, got {status}")

        self.status = status
        self.location = location
        super().__init__(f"Redirect {status} to {location}")


def redirect(status: int, location: str) -> None:
    """
    Trigger a navigation redirect.

    Args:
        status: HTTP redirect status code (300-308)
        location: Destination URL or path

    Example:
```python
        @form
        async def create_post(title: str) -> None:
            post_id = await db.insert(title)
            redirect(303, f'/posts/{post_id}')
```
    """
    raise Redirect(status, location)


def error(status: int, message: str) -> HTTPError:
    """
    Raise an HTTP error with a custom message.

    Args:
        status: HTTP status code (400-599)
        message: User-facing error message

    Raises:
        HTTPError: Always raises

    Example:
        ```python
        @query
        async def get_user(user_id: str) -> User:
            user = await db.get_user(user_id)
            if not user:
                raise error(404, 'User not found')
            return user
        ```
    """
    raise HTTPError(status, message)
