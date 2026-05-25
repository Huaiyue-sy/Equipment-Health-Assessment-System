from __future__ import annotations

import csv
import os
import time
from dataclasses import asdict

import paho.mqtt.client as mqtt

from .mqtt_transport import MqttConfig, loads_payload, make_client
from .schemas import TelemetryPoint


class MqttCsvCollector:
    def __init__(self, out_path: str) -> None:
        self.out_path = out_path
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        self._file = open(out_path, "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=["ts_ms", "asset_id", "point", "value", "quality"])
        self._writer.writeheader()
        self._n = 0

    def close(self) -> None:
        try:
            self._file.close()
        except Exception:
            pass

    @property
    def count(self) -> int:
        return self._n

    def _handle(self, _client: mqtt.Client, _userdata, msg: mqtt.MQTTMessage) -> None:
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
        self._writer.writerow(asdict(p))
        self._n += 1

    def collect(
        self,
        *,
        mqtt_cfg: MqttConfig,
        topic_filter: str = "telemetry/raw/#",
        duration_s: float = 10.0,
        max_messages: int | None = None,
    ) -> int:
        client = make_client(client_id="sim-collector", cfg=mqtt_cfg, on_message=self._handle)

        done = {"stop": False}

        def on_connect(c: mqtt.Client, _userdata, _flags, reason_code, _properties=None):
            if reason_code != 0:
                raise RuntimeError(f"MQTT connect failed: {reason_code}")
            c.subscribe(topic_filter, qos=0)

        client.on_connect = on_connect
        client.loop_start()

        start = time.time()
        while True:
            if max_messages is not None and self._n >= max_messages:
                break
            if time.time() - start >= duration_s:
                break
            time.sleep(0.02)

        client.loop_stop()
        client.disconnect()
        return self._n
