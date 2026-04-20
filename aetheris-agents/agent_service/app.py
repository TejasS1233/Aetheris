from __future__ import annotations

from agent_service.transport.mqtt_bus import MqttBus


def run() -> None:
    bus = MqttBus()
    bus.run()
