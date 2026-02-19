import asyncio
from fluidkit.context import FluidKitContext, set_context, get_context, reset_context

async def test_basic():
    # Create and set context
    ctx = FluidKitContext()
    token = set_context(ctx)
    
    # Add some data
    ctx.add_refresh("get_posts", {}, [{"id": "1", "title": "Post"}])
    ctx.add_set("get_user", {"user_id": "123"}, {"id": "123", "name": "Jane"})
    
    # Retrieve from context
    retrieved = get_context()
    print("Refreshed:", retrieved.refreshed)
    print("Set:", retrieved.set_data)
    
    # Clean up
    reset_context(token)
    print("✅ Basic test passed!")

async def test_isolation():
    """Test that two async tasks have separate contexts"""
    async def task1():
        ctx1 = FluidKitContext()
        token = set_context(ctx1)
        ctx1.add_refresh("task1_query", {}, "task1_data")
        await asyncio.sleep(0.01)  # Simulate async work
        assert get_context().refreshed["task1_query"].data == "task1_data"
        reset_context(token)
    
    async def task2():
        ctx2 = FluidKitContext()
        token = set_context(ctx2)
        ctx2.add_refresh("task2_query", {}, "task2_data")
        await asyncio.sleep(0.01)
        assert get_context().refreshed["task2_query"].data == "task2_data"
        reset_context(token)
    
    # Run concurrently
    await asyncio.gather(task1(), task2())
    print("✅ Isolation test passed!")

if __name__ == "__main__":
    asyncio.run(test_basic())
    asyncio.run(test_isolation())
