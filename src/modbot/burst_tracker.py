"""In-memory tracker for detecting duplicated messages.

The spam we care about is literal copy-paste: the same message posted into many
channels in a short burst, or repeated in one channel. We fingerprint each
message (see :mod:`modbot.fingerprint`) and record *where* and *when* we saw it,
entirely in memory with a short retention window.

This replaces the old fuzzy "self-repeat" check. Fuzzy similarity is still used,
but only against the *learned* spam database, where it generalizes to reworded
variants. For live duplicate detection, an exact fingerprint is faster and a
better match for the copy-paste threat.
"""

import time
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Occurrence:
    channel_id: int
    message_id: int
    timestamp: float


class BurstTracker:
    def __init__(
        self,
        *,
        retention_seconds: float = 120.0,
        burst_window_seconds: float = 60.0,
        burst_channels: int = 2,
        repeat_count: int = 2,
    ):
        self.retention_seconds = retention_seconds
        self.burst_window_seconds = burst_window_seconds
        self.burst_channels = burst_channels
        self.repeat_count = repeat_count
        self._events: dict[tuple[int, str], deque[Occurrence]] = defaultdict(deque)

    def record(
        self,
        user_id: int,
        content_hash: str,
        channel_id: int,
        message_id: int,
        *,
        now: float | None = None,
    ) -> Occurrence:
        """Record that ``user_id`` posted a message with ``content_hash``."""
        now = time.time() if now is None else now
        key = (user_id, content_hash)
        occurrence = Occurrence(channel_id, message_id, now)
        self._events[key].append(occurrence)
        self._prune(key, now)
        return occurrence

    def _prune(self, key: tuple[int, str], now: float) -> None:
        events = self._events[key]
        cutoff = now - self.retention_seconds
        while events and events[0].timestamp < cutoff:
            events.popleft()
        if not events:
            self._events.pop(key, None)

    def _recent(
        self, user_id: int, content_hash: str, within: float, now: float
    ) -> list[Occurrence]:
        events = self._events.get((user_id, content_hash))
        if not events:
            return []
        threshold = now - within
        return [o for o in events if o.timestamp >= threshold]

    def is_burst(
        self, user_id: int, content_hash: str, *, now: float | None = None
    ) -> bool:
        """True if the same message hit >= ``burst_channels`` distinct channels."""
        now = time.time() if now is None else now
        recent = self._recent(user_id, content_hash, self.burst_window_seconds, now)
        channels = {o.channel_id for o in recent}
        return len(channels) >= self.burst_channels

    def is_repeat(
        self, user_id: int, content_hash: str, *, now: float | None = None
    ) -> bool:
        """True if the same message was posted >= ``repeat_count`` times."""
        now = time.time() if now is None else now
        recent = self._recent(user_id, content_hash, self.burst_window_seconds, now)
        return len(recent) >= self.repeat_count

    def occurrences(
        self, user_id: int, content_hash: str, *, now: float | None = None
    ) -> list[Occurrence]:
        """Return recent occurrences (for deleting every copy on a trigger)."""
        now = time.time() if now is None else now
        return self._recent(user_id, content_hash, self.burst_window_seconds, now)

    def clear(self, user_id: int, content_hash: str) -> None:
        """Forget a fingerprint after acting on it, so it does not re-trigger."""
        self._events.pop((user_id, content_hash), None)
