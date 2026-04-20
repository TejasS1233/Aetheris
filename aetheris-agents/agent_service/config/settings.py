from __future__ import annotations

import os

from dotenv import load_dotenv


load_dotenv()


class Settings:
    mqtt_broker: str = os.getenv("MQTT_BROKER", "localhost")
    mqtt_port: int = int(os.getenv("MQTT_PORT", "1883"))
    exceptions_topic: str = os.getenv("EXCEPTIONS_TOPIC", "aetheris/exceptions")
    commands_topic: str = os.getenv("COMMANDS_TOPIC", "aetheris/commands")
    discussion_topic: str = os.getenv("DISCUSSION_TOPIC", "aetheris/internal/discussion")
    consensus_topic: str = os.getenv("CONSENSUS_TOPIC", "aetheris/consensus")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    immediate_stream: str = os.getenv("REDIS_IMMEDIATE_STREAM", "aetheris:stream:immediate")
    batch_stream: str = os.getenv("REDIS_BATCH_STREAM", "aetheris:stream:batch")
    consumer_group: str = os.getenv("REDIS_CONSUMER_GROUP", "aetheris-agents")
    consumer_name: str = os.getenv("REDIS_CONSUMER_NAME", "orchestrator-1")
    immediate_score_threshold: float = float(os.getenv("IMMEDIATE_SCORE_THRESHOLD", "0.9"))
    batch_size: int = int(os.getenv("BATCH_SIZE", "10"))
    immediate_batch_size: int = int(os.getenv("IMMEDIATE_BATCH_SIZE", "5"))
    immediate_batch_max_wait_ms: int = int(os.getenv("IMMEDIATE_BATCH_MAX_WAIT_MS", "150"))
    batch_max_wait_ms: int = int(os.getenv("BATCH_MAX_WAIT_MS", "300"))
    mongodb_uri: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    mongodb_database: str = os.getenv("MONGODB_DATABASE", "aetheris")


settings = Settings()
