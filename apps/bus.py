"""In-process event bus (design Section 12.2).

Provides pub/sub with monotonic event ids per job so the UI can resume progress streams. The
interface (publish/subscribe) matches what a NATS JetStream adapter will expose, so swapping to
NATS later does not change producers/consumers. Owner: Pushp/Tarun.
"""
from __future__ import annotations

import itertools
import threading
from collections import defaultdict
from collections.abc import Callable

from processiq_shared.events import Event

_lock = threading.RLock()
_counter = itertools.count(1)
_subscribers: dict[str, list[Callable[[Event], None]]] = defaultdict(list)
# Per-job event log so late subscribers can replay (design §10.3 resumable stream).
_job_log: dict[str, list[Event]] = defaultdict(list)


def publish(event: Event) -> Event:
    with _lock:
        event.event_id = next(_counter)
        _subscribers_snapshot = list(_subscribers.get(event.subject, []))
        if event.job_id:
            _job_log[event.job_id].append(event)
    for cb in _subscribers_snapshot:
        cb(event)
    return event


def subscribe(subject: str, cb: Callable[[Event], None]) -> None:
    with _lock:
        _subscribers[subject].append(cb)


def replay(job_id: str, after_event_id: int = 0) -> list[Event]:
    with _lock:
        return [e for e in _job_log.get(job_id, []) if e.event_id > after_event_id]
