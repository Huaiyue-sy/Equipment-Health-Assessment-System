from __future__ import annotations

import threading
import time
from typing import Callable

import paho.mqtt.client as mqtt

from .mqtt_transport import MqttConfig, loads_payload, make_client
from .schemas import TelemetryPoint
from .scoring import OnlineScorer


def start_ingest(
    *,
    mqtt_cfg: MqttConfig,
    scorer: OnlineScorer,
    topic_filter: str = "telemetry/raw/#",
) -> Callable[[], None]:
    """后台订阅 MQTT 并持续 ingest 到 scorer。返回 stop()。"""

    stop_flag = {"stop": False}

    def _on_message(_client: mqtt.Client, _userdata, msg: mqtt.MQTTMessage) -> None:
        try:
            d = loads_payload(msg.payload)
            p = TelemetryPoint(
                ts_ms=int(d["ts_ms"]),
                asset_id=str(d["asset_id"]),
                point=str(d["point"]),
                value=float(d["value"]),
                quality=str(d.get("quality", "good")),
            )
        except Exception:
            return
        scorer.ingest(p)

    client = make_client(client_id="sim-api-ingest", cfg=mqtt_cfg, on_message=_on_message)

    def on_connect(c: mqtt.Client, _userdata, _flags, reason_code, _properties=None):
        if reason_code != 0:
            raise RuntimeError(f"MQTT connect failed: {reason_code}")
        c.subscribe(topic_filter, qos=0)

    client.on_connect = on_connect

    def loop():
        client.loop_start()
        try:
            while not stop_flag["stop"]:
                time.sleep(0.2)
        finally:
            client.loop_stop()
            client.disconnect()

    t = threading.Thread(target=loop, daemon=True)
    t.start()

    def stop() -> None:
        stop_flag["stop"] = True

    return stop
