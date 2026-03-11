"""
Event Store
============
A simple in-memory store that collects recent RFID events.
Think of it as the AI layer's "short-term memory".

When enough events accumulate (or enough time passes), the anomaly
detector reads them all, sends them to Claude for analysis, and then
clears the store to start fresh.

Why not just use a list?
- Thread safety: multiple MQTT messages can arrive at the same time,
  so we use a Lock to prevent data corruption.
- Size limit: we cap the memory at MAX_EVENTS_IN_MEMORY so it doesn't
  grow forever.
- Separation: keeping this in its own file makes the code cleaner
  and easier to test.
"""

import threading
from datetime import datetime, timezone

import config


class EventStore:
    """
    Thread-safe store for recent RFID events.

    Usage:
        store = EventStore()
        store.add(event_dict)           # Add an event
        events = store.get_all()        # Read all events
        store.clear()                   # Empty the store
        if store.should_analyze():      # Check if it's time for AI analysis
            ...
    """

    def __init__(self, demo_mode: bool = False):
        # The list where events are stored
        self._events = []

        # A lock to make this thread-safe
        # (multiple MQTT messages can arrive simultaneously)
        self._lock = threading.Lock()

        # Track when the last analysis happened
        self._last_analysis_time = datetime.now(timezone.utc)

        # Use demo or production thresholds
        if demo_mode:
            self._event_threshold = config.DEMO_ANALYSIS_EVENT_THRESHOLD
            self._time_threshold = config.DEMO_ANALYSIS_INTERVAL_SECONDS
        else:
            self._event_threshold = config.ANALYSIS_EVENT_THRESHOLD
            self._time_threshold = config.ANALYSIS_INTERVAL_SECONDS

    def add(self, event: dict) -> int:
        """
        Add an RFID event to the store.

        Parameters:
            event: A dict containing the MQTT message (GRHBPKT or GRTAGDATA)

        Returns:
            The current number of events in the store.
        """
        with self._lock:
            self._events.append(event)

            # If we've exceeded the memory limit, drop the oldest event
            if len(self._events) > config.MAX_EVENTS_IN_MEMORY:
                self._events.pop(0)

            return len(self._events)

    def get_all(self) -> list[dict]:
        """
        Get a copy of all stored events.
        Returns a copy so the caller can't accidentally modify our store.
        """
        with self._lock:
            return list(self._events)

    def clear(self):
        """Empty the store and reset the analysis timer."""
        with self._lock:
            self._events.clear()
            self._last_analysis_time = datetime.now(timezone.utc)

    def count(self) -> int:
        """Return the number of events currently stored."""
        with self._lock:
            return len(self._events)

    def should_analyze(self) -> bool:
        """
        Check if it's time to trigger an AI analysis.

        Returns True if EITHER condition is met:
          1. We have accumulated enough events (threshold reached)
          2. Enough time has passed since the last analysis

        This is how we balance cost vs responsiveness:
        - We don't call Claude on every single event (too expensive)
        - But we don't wait too long either (might miss anomalies)
        """
        with self._lock:
            # Condition 1: enough events accumulated
            if len(self._events) >= self._event_threshold:
                return True

            # Condition 2: enough time has passed (and we have at least 1 event)
            if len(self._events) > 0:
                elapsed = (
                    datetime.now(timezone.utc) - self._last_analysis_time
                ).total_seconds()
                if elapsed >= self._time_threshold:
                    return True

            return False

    def get_summary(self) -> dict:
        """
        Get a quick summary of what's in the store.
        Useful for logging.
        """
        with self._lock:
            tag_events = [e for e in self._events if e.get("TYP") == "GRTAGDATA"]
            health_events = [e for e in self._events if e.get("TYP") == "GRHBPKT"]

            # Count directions
            in_count = sum(
                1 for e in tag_events
                if e.get("READPOINT", "").endswith(".IN")
            )
            out_count = sum(
                1 for e in tag_events
                if e.get("READPOINT", "").endswith(".OUT")
            )

            # Count unique gate readers
            reader_ids = set(e.get("GATE_READER_ID", "") for e in self._events)

            return {
                "total_events": len(self._events),
                "tag_events": len(tag_events),
                "health_events": len(health_events),
                "in_count": in_count,
                "out_count": out_count,
                "unique_readers": len(reader_ids),
            }