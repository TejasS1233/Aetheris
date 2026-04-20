from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class Counters:
    queued_immediate: int = 0
    queued_batch: int = 0
    processed_immediate: int = 0
    processed_batch: int = 0
    command_block: int = 0
    command_review: int = 0
    command_approve: int = 0
    ingest_errors: int = 0
    process_errors: int = 0


class MetricLogger:
    def __init__(self, interval_seconds: int = 5) -> None:
        self.interval_seconds = interval_seconds
        self.counters = Counters()
        self._last_report = time.time()

    def tick(self) -> None:
        now = time.time()
        if now - self._last_report < self.interval_seconds:
            return
        self._last_report = now
        c = self.counters
        print(
            "[metrics] "
            f"queued(immediate={c.queued_immediate}, batch={c.queued_batch}) "
            f"processed(immediate={c.processed_immediate}, batch={c.processed_batch}) "
            f"commands(block={c.command_block}, review={c.command_review}, approve={c.command_approve}) "
            f"errors(ingest={c.ingest_errors}, process={c.process_errors})"
        )
