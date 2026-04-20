from __future__ import annotations

import json
from typing import Iterable

from redis import Redis

from agent_service.config.settings import settings
from agent_service.models.schema import ExceptionEvent


class PriorityBuffer:
    def __init__(self, redis_client: Redis) -> None:
        self.redis = redis_client

    def score(self, event: ExceptionEvent) -> float:
        z_component = min(abs(event.z_score) / 6.0, 1.0)
        amount_component = min(event.amount / 5000.0, 1.0)
        return round((0.7 * z_component) + (0.3 * amount_component), 4)

    def enqueue(self, event: ExceptionEvent) -> tuple[str, float]:
        suspicion = self.score(event)
        target = settings.immediate_stream if suspicion >= settings.immediate_score_threshold else settings.batch_stream
        self.redis.xadd(
            target,
            {
                "payload": event.model_dump_json(by_alias=True),
                "suspicion": str(suspicion),
            },
        )
        return target, suspicion

    def _ensure_group(self, stream_name: str) -> None:
        try:
            self.redis.xgroup_create(stream_name, settings.consumer_group, id="0", mkstream=True)
        except Exception:
            # Group likely exists already.
            pass

    def init_groups(self) -> None:
        self._ensure_group(settings.immediate_stream)
        self._ensure_group(settings.batch_stream)

    def pop_immediate(self):
        items = self.redis.xreadgroup(
            settings.consumer_group,
            settings.consumer_name,
            {settings.immediate_stream: ">"},
            count=1,
            block=1000,
        )
        return self._flatten(items)

    def pop_batch(self, count: int):
        items = self.redis.xreadgroup(
            settings.consumer_group,
            settings.consumer_name,
            {settings.batch_stream: ">"},
            count=count,
            block=1000,
        )
        return self._flatten(items)

    def ack(self, stream_name: str, message_id: str) -> None:
        self.redis.xack(stream_name, settings.consumer_group, message_id)

    def _flatten(self, raw) -> list[tuple[str, str, ExceptionEvent, float]]:
        result: list[tuple[str, str, ExceptionEvent, float]] = []
        for stream_name, entries in raw:
            for message_id, fields in entries:
                payload = fields.get("payload")
                suspicion = float(fields.get("suspicion", "0"))
                if payload is None:
                    continue
                if isinstance(payload, bytes):
                    payload = payload.decode("utf-8")
                event = ExceptionEvent.model_validate(json.loads(payload))
                if isinstance(stream_name, bytes):
                    stream_name = stream_name.decode("utf-8")
                if isinstance(message_id, bytes):
                    message_id = message_id.decode("utf-8")
                result.append((stream_name, message_id, event, suspicion))
        return result
