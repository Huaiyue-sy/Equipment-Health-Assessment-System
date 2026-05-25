from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable

import paho.mqtt.client as mqtt


@dataclass(frozen=True)
class MqttConfig:
    host: str = "127.0.0.1"
    port: int = 1883
    username: str | None = None
    password: str | None = None
    base_topic: str = "telemetry/raw"
    keepalive: int = 60


def make_client(
    *,
    client_id: str,
    cfg: MqttConfig,
    on_message: Callable[[mqtt.Client, Any, mqtt.MQTTMessage], None] | None = None,
) -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id, clean_session=True)
    if cfg.username is not None:
        client.username_pw_set(cfg.username, cfg.password)
    if on_message is not None:
        client.on_message = on_message

    client.connect(cfg.host, cfg.port, keepalive=cfg.keepalive)
    return client


def topic_for_asset(cfg: MqttConfig, asset_id: str) -> str:
    return f"{cfg.base_topic}/{asset_id}"


def dumps_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def loads_payload(b: bytes) -> dict[str, Any]:
    return json.loads(b.decode("utf-8"))


def wait_until(predicate: Callable[[], bool], timeout_s: float = 5.0) -> None:
    start = time.time()
    while time.time() - start < timeout_s:
        if predicate():
            return
        time.sleep(0.01)
    raise TimeoutError("timeout waiting for condition")
