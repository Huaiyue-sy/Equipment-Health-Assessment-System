from __future__ import annotations

import time

import paho.mqtt.client as mqtt

from .mqtt_transport import MqttConfig, loads_payload, make_client
from .schemas import TelemetryPoint
from .scoring import OnlineScorer


def live_score(
    *,
    mqtt_cfg: MqttConfig,
    scorer: OnlineScorer,
    topic_filter: str = "telemetry/raw/#",
    duration_s: float = 60.0,
    on_result=None,
) -> None:
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

        hr = scorer.ingest(p)
        if hr is not None and on_result is not None:
            on_result(hr)

    client = make_client(client_id="sim-live-score", cfg=mqtt_cfg, on_message=_on_message)

    def on_connect(c: mqtt.Client, _userdata, _flags, reason_code, _properties=None):
        if reason_code != 0:
            raise RuntimeError(f"MQTT connect failed: {reason_code}")
        c.subscribe(topic_filter, qos=0)

    client.on_connect = on_connect
    client.loop_start()

    start = time.time()
    while time.time() - start < duration_s:
        time.sleep(0.05)

    client.loop_stop()
    client.disconnect()
