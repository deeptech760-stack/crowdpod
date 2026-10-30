"""Run events: saved to the store and pushed to live subscribers (SSE)."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from .models import RunEvent
from .store import Store

TERMINAL = {"run.finished", "run.failed"}


class EventBus:
    def __init__(self, store: Store):
        self.store = store
        self._seq: dict[str, int] = defaultdict(int)
        self._subs: dict[str, set[asyncio.Queue[RunEvent]]] = defaultdict(set)

    def emitter(self, run_id: str):
        async def emit(type_: str, data: dict[str, Any] | None = None) -> None:
            self._seq[run_id] += 1
            event = RunEvent(seq=self._seq[run_id], run_id=run_id, type=type_, data=data or {})
            self.store.save_event(event)
            for q in list(self._subs[run_id]):
                q.put_nowait(event)

        return emit

    def subscribe(self, run_id: str) -> asyncio.Queue[RunEvent]:
        q: asyncio.Queue[RunEvent] = asyncio.Queue()
        self._subs[run_id].add(q)
        return q

    def unsubscribe(self, run_id: str, q: asyncio.Queue[RunEvent]) -> None:
        self._subs[run_id].discard(q)
