import asyncio

from fluidkit.context import FluidKitContext, get_context, reset_context, set_context
from fluidkit.models import MutationType


async def test_basic():
    ctx = FluidKitContext()
    token = set_context(ctx)

    ctx.add_mutation(MutationType.REFRESH, "get_posts", {}, [{"id": "1", "title": "Post"}])
    ctx.add_mutation(MutationType.SET, "get_user", {"user_id": "123"}, {"id": "123", "name": "Jane"})

    retrieved = get_context()
    assert len(retrieved.mutations) == 2
    assert retrieved.mutations[0].mutation_type == MutationType.REFRESH
    assert retrieved.mutations[0].key == "get_posts"
    assert retrieved.mutations[1].mutation_type == MutationType.SET
    assert retrieved.mutations[1].key == "get_user"

    reset_context(token)
    print("Basic test passed")


async def test_isolation():
    """Test that two async tasks have separate contexts."""

    async def task1():
        ctx = FluidKitContext()
        token = set_context(ctx)
        ctx.add_mutation(MutationType.REFRESH, "task1_query", {}, "task1_data")
        await asyncio.sleep(0.01)
        retrieved = get_context()
        assert retrieved.mutations[0].data == "task1_data"
        reset_context(token)

    async def task2():
        ctx = FluidKitContext()
        token = set_context(ctx)
        ctx.add_mutation(MutationType.REFRESH, "task2_query", {}, "task2_data")
        await asyncio.sleep(0.01)
        retrieved = get_context()
        assert retrieved.mutations[0].data == "task2_data"
        reset_context(token)

    await asyncio.gather(task1(), task2())
    print("Isolation test passed")


if __name__ == "__main__":
    asyncio.run(test_basic())
    asyncio.run(test_isolation())
