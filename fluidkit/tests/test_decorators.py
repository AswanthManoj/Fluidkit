from fluidkit import app, query, command, form, prerender, error, Redirect, FileUpload, RequestEvent

# =============================================================================
# Test @query
# =============================================================================

@query
async def get_user(user_id: str):
    """Get a user by ID"""
    if user_id == "invalid":
        raise error(404, "User not found")
    return {"id": user_id, "name": "John Doe", "email": "john@example.com"}

@query
async def get_protected_data(request: RequestEvent):
    """Query with request context"""
    session = request.cookies.get("session")
    if not session:
        raise error(401, "Unauthorized")
    return {"data": "secret", "session": session}

# =============================================================================
# Test @command
# =============================================================================

_posts_cache = [
    {"id": "1", "title": "First Post", "likes": 5},
    {"id": "2", "title": "Second Post", "likes": 10}
]

@query
async def get_posts():
    """Get all posts"""
    return _posts_cache

@command
async def add_like(post_id: str):
    """Add like and refresh posts cache"""
    # Simulate incrementing like
    for post in _posts_cache:
        if post["id"] == post_id:
            post["likes"] += 1
    
    # Refresh client cache
    await get_posts().refresh()
    
    return {"success": True}

@command
async def create_post(title: str, request: RequestEvent):
    """Command with redirect"""
    new_post = {"id": str(len(_posts_cache) + 1), "title": title, "likes": 0}
    _posts_cache.append(new_post)
    
    request.cookies.set("last_action", "created_post")
    await get_posts().refresh()
    
    raise Redirect(303, f"/posts/{new_post['id']}")

# =============================================================================
# Test @form
# =============================================================================

from pydantic import BaseModel

class UserProfile(BaseModel):
    name: str
    email: str
    age: int

@form
async def upload_simple(title: str, description: str):
    """Simple form without files"""
    return {"title": title, "description": description}

@form
async def upload_with_file(title: str, photo: FileUpload):
    """Form with file upload"""
    return {
        "title": title,
        "filename": photo.filename,
        "size": photo.size,
        "content_type": photo.content_type
    }

@form
async def upload_complex(user: UserProfile, tags: list[str], photo: FileUpload):
    """Complex form with model + file"""
    return {
        "user": user.model_dump(),
        "tags": tags,
        "photo": photo.filename
    }

# =============================================================================
# Test @prerender
# =============================================================================

@prerender
async def get_static_posts():
    """Prerender without params"""
    return [
        {"id": "1", "title": "Static Post 1"},
        {"id": "2", "title": "Static Post 2"}
    ]

@prerender(inputs=['post-1', 'post-2', 'post-3'])
async def get_static_post(slug: str):
    """Prerender with static inputs"""
    return {"slug": slug, "title": f"Post {slug}", "content": "Lorem ipsum"}

async def get_all_slugs():
    """Dynamic inputs function"""
    return ['dynamic-1', 'dynamic-2', 'dynamic-3']

@prerender(inputs=get_all_slugs, dynamic=True)
async def get_dynamic_post(slug: str):
    """Prerender with dynamic inputs"""
    return {"slug": slug, "title": f"Dynamic {slug}"}


# =============================================================================
# Run server
# =============================================================================

if __name__ == "__main__":
    from fluidkit import run
    print("\n" + "="*60)
    print("FluidKit Test Server")
    print("="*60)
    print("Visit: http://localhost:8000/docs")
    print("\nTest endpoints:")
    print("  GET  /remote/get_user")
    print("  GET  /remote/get_protected_data")
    print("  GET  /remote/get_posts")
    print("  POST /remote/add_like")
    print("  POST /remote/create_post")
    print("  POST /remote/upload_simple")
    print("  POST /remote/upload_with_file")
    print("  POST /remote/upload_complex")
    print("  GET  /remote/get_static_posts")
    print("  GET  /remote/get_static_post")
    print("  GET  /remote/get_dynamic_post")
    print("="*60 + "\n")
    
    run()
