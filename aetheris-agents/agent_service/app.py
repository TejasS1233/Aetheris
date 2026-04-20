from __future__ import annotations

import socket

from pymongo import MongoClient
from redis import Redis

from agent_service.config.settings import settings
from agent_service.transport.mqtt_bus import MqttBus


def _healthcheck() -> None:
    Redis.from_url(settings.redis_url, decode_responses=True).ping()
    MongoClient(settings.mongodb_uri).admin.command("ping")
    with socket.create_connection((settings.mqtt_broker, settings.mqtt_port), timeout=3):
        pass


def run() -> None:
    if settings.fail_fast_healthcheck:
        _healthcheck()
        print("[agents] Healthcheck OK (MQTT, Redis, MongoDB)")

    bus = MqttBus()
    bus.run()
