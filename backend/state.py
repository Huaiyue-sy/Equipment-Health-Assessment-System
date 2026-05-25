from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import asdict

from ihealthsim.schemas import AlarmEvent, HealthResult, TelemetryPoint


class InMemoryState:
    def __init__(self, *, max_points: int = 2000) -> None:
        self._lock = threading.Lock()
        self._latest_by_point: dict[str, dict[str, TelemetryPoint]] = defaultdict(dict)  # asset -> point -> TelemetryPoint
        self._ring: dict[str, deque[TelemetryPoint]] = defaultdict(lambda: deque(maxlen=max_points))
        self._health_latest: dict[str, HealthResult] = {}
        self._health_history: dict[str, deque[dict]] = defaultdict(lambda: deque(maxlen=500))  # 健康分历史
        self._alarm_history: dict[str, deque[dict]] = defaultdict(lambda: deque(maxlen=200))   # 报警历史
        self._mqtt_connected: bool = False
        self._last_msg_ts: float | None = None
        self._model_loaded: bool = False
        self._started_at: float = time.time()

    def set_mqtt_connected(self, connected: bool) -> None:
        with self._lock:
            self._mqtt_connected = connected

    def mark_model_loaded(self) -> None:
        with self._lock:
            self._model_loaded = True

    def ingest_point(self, p: TelemetryPoint) -> None:
        with self._lock:
            self._latest_by_point[p.asset_id][p.point] = p
            self._ring[p.asset_id].append(p)
            self._last_msg_ts = time.time()

    def set_health(self, hr: HealthResult) -> None:
        with self._lock:
            self._health_latest[hr.asset_id] = hr
            self._health_history[hr.asset_id].append({
                "ts_ms": hr.ts_ms,
                "health_level": hr.health_level,
                "health_score": hr.health_score,
            })

    def add_alarm(self, alarm: AlarmEvent) -> None:
        with self._lock:
            self._alarm_history[alarm.asset_id].append(asdict(alarm))

    def snapshot(self, asset_id: str | None = None) -> dict:
        with self._lock:
            assets = [asset_id] if asset_id else list(self._latest_by_point.keys())
            telemetry = {}
            ring = {}
            health = {}
            for a in assets:
                telemetry[a] = {k: asdict(v) for k, v in self._latest_by_point.get(a, {}).items()}
                ring[a] = [asdict(x) for x in list(self._ring.get(a, []))]
                if a in self._health_latest:
                    health[a] = asdict(self._health_latest[a])

            return {
                "started_at": self._started_at,
                "mqtt_connected": self._mqtt_connected,
                "model_loaded": self._model_loaded,
                "last_message_at": self._last_msg_ts,
                "assets": assets,
                "telemetry_latest": telemetry,
                "telemetry_ring": ring,
                "health_latest": health,
            }

    def health_trend(self, asset_id: str) -> list[dict]:
        with self._lock:
            return list(self._health_history.get(asset_id, []))

    def alarm_trend(self, asset_id: str) -> list[dict]:
        with self._lock:
            return list(self._alarm_history.get(asset_id, []))
