from fluidkit import command, form, query

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
