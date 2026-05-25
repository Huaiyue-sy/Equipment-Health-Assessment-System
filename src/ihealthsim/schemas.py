from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TelemetryPoint:
    ts_ms: int
    asset_id: str
    point: str
    value: float
    quality: str = "good"


@dataclass(frozen=True)
class HealthResult:
    ts_ms: int
    asset_id: str
    health_level: int  # 0..3
    health_score: float  # 0..100
    proba: list[float]
    explanation: str
    telemetry: dict | None = None  # 遥测快照: {vib_rms, temp_c, motor_current_a, rpm}


@dataclass(frozen=True)
class AlarmEvent:
    ts_ms: int
    asset_id: str
    rule_name: str
    rule_type: str  # "threshold" | "trend" | "combination"
    severity: str  # "warning" | "critical"
    message: str
