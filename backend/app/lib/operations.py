"""In-process operation queue registry.

Each long-running operation (archive, restore) is assigned a UUID op_id and an
asyncio.Queue.  The background task puts serialised JSON event strings into the
queue; the SSE stream endpoint drains it.  A sentinel object signals completion.

The registry lives for the lifetime of the process.  On reconnect after a crash
the op_id will be unknown and the client will get a 404, which is acceptable —
the operation DB log can be checked for final status.
"""
import asyncio
import uuid

# Sentinel signals the SSE consumer that the operation has finished.
SENTINEL: object = object()

# op_id → asyncio.Queue[str | SENTINEL]
_registry: dict[str, asyncio.Queue] = {}


def new_operation() -> tuple[str, asyncio.Queue]:
    """Create a new (op_id, queue) pair and register it."""
    op_id = str(uuid.uuid4())
    q: asyncio.Queue = asyncio.Queue()
    _registry[op_id] = q
    return op_id, q


def get_queue(op_id: str) -> "asyncio.Queue | None":
    return _registry.get(op_id)


def finish_operation(op_id: str) -> None:
    """Put SENTINEL into the queue so the consumer exits, then remove from registry."""
    q = _registry.pop(op_id, None)
    if q is not None:
        q.put_nowait(SENTINEL)
