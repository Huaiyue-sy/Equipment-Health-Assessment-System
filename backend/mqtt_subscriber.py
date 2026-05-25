from __future__ import annotations

import threading
from dataclasses import asdict

import paho.mqtt.client as mqtt

from ihealthsim.mqtt_transport import MqttConfig, loads_payload
from ihealthsim.schemas import TelemetryPoint

from .sse import SseHub
from .state import InMemoryState


class MqttSubscriber:
    def __init__(
        self,
        *,
        cfg: MqttConfig,
        topic_filter: str,
        state: InMemoryState,
        hub: SseHub,
        on_point=None,
    ) -> None:
        self.cfg = cfg
        self.topic_filter = topic_filter
        self.state = state
        self.hub = hub
        self.on_point = on_point

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="flask-backend-sub", clean_session=True)
        if self.cfg.username is not None:
            self._client.username_pw_set(self.cfg.username, self.cfg.password)

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        self._thread: threading.Thread | None = None

    def start(self) -> None:
        try:
            self._client.connect(self.cfg.host, self.cfg.port, keepalive=self.cfg.keepalive)
        except Exception as e:
            self.state.set_mqtt_connected(False)
            self.hub.publish("flow", {"stage": "mqtt", "status": "connect_failed", "error": str(e)})
            return
        self._client.loop_start()

    def stop(self) -> None:
        try:
            self._client.loop_stop()
        finally:
            try:
                self._client.disconnect()
            except Exception:
                pass

    def _on_connect(self, client: mqtt.Client, _userdata, _flags, reason_code, _properties=None):
        if reason_code == 0:
            self.state.set_mqtt_connected(True)
            client.subscribe(self.topic_filter, qos=0)
            self.hub.publish("flow", {"stage": "mqtt", "status": "connected"})
        else:
            self.state.set_mqtt_connected(False)
            self.hub.publish("flow", {"stage": "mqtt", "status": "error", "reason_code": reason_code})

    def _on_disconnect(self, _client: mqtt.Client, _userdata, flags, reason_code, properties=None):
        self.state.set_mqtt_connected(False)
        self.hub.publish("flow", {"stage": "mqtt", "status": "disconnected", "reason_code": reason_code})

    def _on_message(self, _client: mqtt.Client, _userdata, msg: mqtt.MQTTMessage) -> None:
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

        self.state.ingest_point(p)
        self.hub.publish("telemetry", asdict(p))
        if self.on_point is not None:
            try:
                self.on_point(p)
            except Exception:
                pass
