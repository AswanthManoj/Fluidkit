# src/lib/test.py
from enum import Enum
from pydantic import BaseModel
from fluidkit import query, command, form, prerender


# ── Models ────────────────────────────────────────────────────────────────


class Post(BaseModel):
    id: int
    title: str
    content: str
    likes: int


class User(BaseModel):
    user_id: str
    display_name: str
    email: str


class UserProfile(BaseModel):
    name: str
    bio: str
    avatar_url: str
    follower_count: int


# ── Query: array of pydantic ─────────────────────────────────────────────


@query
async def get_posts() -> list[Post]:
    """Fetch all blog posts."""
    return []


# ── Query: array of primitive ────────────────────────────────────────────


@query
async def get_tags() -> list[str]:
    """Fetch all available tags."""
    return []


# ── Query: single pydantic (no params) ───────────────────────────────────


@query
async def get_current_user() -> User:
    """Get the currently authenticated user."""
    return User(user_id="u1", display_name="Alice", email="alice@test.com")


# ── Query: single pydantic (with param) ──────────────────────────────────


@query
async def get_user(user_id: str) -> User:
    """Look up a user by ID."""
    return User(user_id=user_id, display_name="Alice", email="alice@test.com")


# ── Query: optional pydantic ─────────────────────────────────────────────


@query
async def find_user(user_id: str) -> User | None:
    """Find a user, returns None if not found."""
    return None


# ── Query: optional primitive ────────────────────────────────────────────


@query
async def get_nickname(user_id: str) -> str | None:
    """Get a user's nickname, if set."""
    return None


# ── Query: single primitive ──────────────────────────────────────────────


@query
async def get_post_count() -> int:
    """Get total number of posts."""
    return 0


# ── Query: record ────────────────────────────────────────────────────────


@query
async def get_stats() -> dict[str, int]:
    """Get site-wide statistics."""
    return {}


# ── Query: void / no return annotation ───────────────────────────────────


@query
async def get_data():
    """Fetch data with no type annotation."""
    return {"key": "value"}


# ── Query: multi param ───────────────────────────────────────────────────


@query
async def search_posts(keyword: str, limit: int, published: bool) -> list[Post]:
    """Search posts with multiple filters."""
    return []


# ── Command: void return ─────────────────────────────────────────────────


@command
async def delete_post(post_id: int) -> None:
    """Delete a post by ID."""
    pass


# ── Command: with return value ───────────────────────────────────────────


@command
async def like_post(post_id: int) -> bool:
    """Like a post, returns True if successful."""
    return True


# ── Command: multi param ─────────────────────────────────────────────────


@command
async def update_post(post_id: int, title: str, content: str) -> Post:
    """Update a post's title and content."""
    return Post(id=post_id, title=title, content=content, likes=0)


# ── Command: no params ───────────────────────────────────────────────────


@command
async def reset_cache() -> None:
    """Clear all cached data."""
    pass


# ── Form: basic fields ───────────────────────────────────────────────────


@form
async def add_post(title: str, content: str):
    """Add a new blog post."""
    pass


# ── Form: with file ──────────────────────────────────────────────────────

from fluidkit.types import FileUpload


@form
async def upload_photo(caption: str, photo: FileUpload):
    """Upload a photo with a caption."""
    pass


# ── Form: single field ───────────────────────────────────────────────────


@form
async def subscribe(email: str):
    """Subscribe to the newsletter."""
    pass


# ── Form: mixed types ────────────────────────────────────────────────────


@form
async def create_profile(name: str, age: int, newsletter: bool):
    """Create a new user profile."""
    pass


# ── Prerender: no params ─────────────────────────────────────────────────


@prerender
async def get_site_config() -> dict[str, str]:
    """Fetch site configuration at build time."""
    return {}


# ── Prerender: with param ────────────────────────────────────────────────


@prerender(inputs=["about", "contact", "faq"], dynamic=True)
async def get_page(slug: str) -> dict[str, str]:
    """Fetch a static page by slug."""
    return {}
