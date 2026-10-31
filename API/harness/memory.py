"""API-harness memory adapter delegating persistence to shared memory."""

from shared.memory import MemoryStore


def open_memory(path: str) -> MemoryStore:
    print("[memory.py] opening persistent memory")
    return MemoryStore(path)
