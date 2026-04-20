from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from pymongo import MongoClient
from redis import Redis

from agent_service.config.settings import settings
from agent_service.control.metrics import MetricLogger
from agent_service.control.priority_buffer import PriorityBuffer
from agent_service.graph.orchestrator import Orchestrator
from agent_service.models.schema import ExceptionEvent


class MqttBus:
    def __init__(self) -> None:
        self.orchestrator = Orchestrator()
        self.redis = Redis.from_url(settings.redis_url, decode_responses=True)
        self.mongo = MongoClient(settings.mongodb_uri)[settings.mongodb_database]
        self.exceptions_coll = self.mongo[settings.mongodb_exceptions_collection]
        self.commands_coll = self.mongo[settings.mongodb_commands_collection]
        self.buffer = PriorityBuffer(self.redis)
        self.buffer.init_groups()
        self._init_mongo_indexes()
        self.metrics = MetricLogger(interval_seconds=5)
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="aetheris-agent-orchestrator")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def _init_mongo_indexes(self) -> None:
        self.exceptions_coll.create_index("transactionId")
        self.exceptions_coll.create_index("receivedAt")
        self.commands_coll.create_index("transaction_id")
        self.commands_coll.create_index("timestamp")

    def _persist_exception(self, event: ExceptionEvent, suspicion: float) -> None:
        try:
            doc = {
                **event.model_dump(by_alias=True),
                "suspicionScore": suspicion,
                "receivedAt": datetime.now(timezone.utc),
            }
            self.exceptions_coll.update_one(
                {"transactionId": event.transaction_id},
                {"$set": doc},
                upsert=True,
            )
        except Exception as exc:
            self.metrics.counters.process_errors += 1
            print(f"[agents] Error persisting exception tx={event.transaction_id}: {exc}")

    def _persist_command(self, command) -> None:
        try:
            doc = command.model_dump()
            doc["storedAt"] = datetime.now(timezone.utc)
            self.commands_coll.update_one(
                {"transaction_id": command.transaction_id},
                {"$set": doc},
                upsert=True,
            )
        except Exception as exc:
            self.metrics.counters.process_errors += 1
            print(f"[agents] Error persisting command tx={command.transaction_id}: {exc}")

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            print("[agents] Connected to MQTT broker")
            client.subscribe(settings.exceptions_topic)
            print(f"[agents] Listening: {settings.exceptions_topic}")
        else:
            print(f"[agents] MQTT connection failed: {reason_code}")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            event = ExceptionEvent.model_validate(payload)
            stream_name, suspicion = self.buffer.enqueue(event)
            self._persist_exception(event, suspicion)
            stream_label = "IMMEDIATE" if stream_name == settings.immediate_stream else "BATCH"
            if stream_label == "IMMEDIATE":
                self.metrics.counters.queued_immediate += 1
            else:
                self.metrics.counters.queued_batch += 1
            print(
                f"[buffer] queued account={event.account_origin} tx={event.transaction_id} "
                f"score={suspicion:.3f} -> {stream_label}"
            )
        except Exception as exc:
            self.metrics.counters.ingest_errors += 1
            print(f"[agents] Error ingesting MQTT message: {exc}")

    def _process_immediate(self) -> None:
        items = self.buffer.pop_immediate(
            settings.immediate_batch_size,
            settings.immediate_batch_max_wait_ms,
        )
        if not items:
            return

        events = [event for _, _, event, _ in items]
        by_tx = {event.transaction_id: (stream_name, message_id, suspicion) for stream_name, message_id, event, suspicion in items}

        try:
            commands = self.orchestrator.investigate_batch(events)
        except Exception as exc:
            self.metrics.counters.process_errors += len(items)
            print(f"[agents] Error processing immediate batch (size={len(items)}): {exc}")
            return

        for command in commands:
            stream_name, message_id, suspicion = by_tx.get(command.transaction_id, (None, None, 0.0))
            if stream_name is None or message_id is None:
                continue

            self.client.publish(settings.commands_topic, command.model_dump_json())
            self._persist_command(command)
            self.buffer.ack(stream_name, message_id)
            self.metrics.counters.processed_immediate += 1
            if command.action == "BLOCK":
                self.metrics.counters.command_block += 1
            elif command.action == "APPROVE":
                self.metrics.counters.command_approve += 1
            else:
                self.metrics.counters.command_review += 1
            print(
                f"[immediate] account={command.account_origin} tx={command.transaction_id} "
                f"action={command.action} score={suspicion:.3f}"
            )

    def _process_batch(self) -> None:
        items = self.buffer.pop_batch(settings.batch_size, settings.batch_max_wait_ms)
        if not items:
            return

        events = [event for _, _, event, _ in items]
        by_tx = {event.transaction_id: (stream_name, message_id, suspicion) for stream_name, message_id, event, suspicion in items}

        try:
            commands = self.orchestrator.investigate_batch(events)
        except Exception as exc:
            self.metrics.counters.process_errors += len(items)
            print(f"[agents] Error processing batch queue (size={len(items)}): {exc}")
            return

        for command in commands:
            stream_name, message_id, suspicion = by_tx.get(command.transaction_id, (None, None, 0.0))
            if stream_name is None or message_id is None:
                continue

            self.client.publish(settings.commands_topic, command.model_dump_json())
            self._persist_command(command)
            self.buffer.ack(stream_name, message_id)
            self.metrics.counters.processed_batch += 1
            if command.action == "BLOCK":
                self.metrics.counters.command_block += 1
            elif command.action == "APPROVE":
                self.metrics.counters.command_approve += 1
            else:
                self.metrics.counters.command_review += 1
            print(
                f"[batch] account={command.account_origin} tx={command.transaction_id} "
                f"action={command.action} score={suspicion:.3f}"
            )

    def _drain_loop(self) -> None:
        while True:
            self._process_immediate()
            self._process_batch()
            self.metrics.tick()
            time.sleep(0.05)

    def run(self) -> None:
        self.client.connect(settings.mqtt_broker, settings.mqtt_port, 60)
        self.client.loop_start()
        self._drain_loop()
