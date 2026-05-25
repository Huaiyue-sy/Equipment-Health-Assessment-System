from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .schemas import AlarmEvent


@dataclass
class ThresholdRule:
    """单点阈值规则：遥测值超过阈值即触发报警。"""
    name: str
    point: str          # 遥测点位名，如 vib_rms, temp_c
    op: str             # ">" 或 "<"
    threshold: float
    severity: str = "warning"  # warning | critical
    message_template: str = "{point} {op} {threshold}: 当前值 {value:.2f}"

    def evaluate(self, ts_ms: int, asset_id: str, telemetry: dict[str, float]) -> AlarmEvent | None:
        val = telemetry.get(self.point)
        if val is None:
            return None
        triggered = False
        if self.op == ">":
            triggered = val > self.threshold
        elif self.op == "<":
            triggered = val < self.threshold
        elif self.op == ">=":
            triggered = val >= self.threshold
        elif self.op == "<=":
            triggered = val <= self.threshold

        if triggered:
            msg = self.message_template.format(point=self.point, op=self.op, threshold=self.threshold, value=val)
            return AlarmEvent(
                ts_ms=ts_ms,
                asset_id=asset_id,
                rule_name=self.name,
                rule_type="threshold",
                severity=self.severity,
                message=msg,
            )
        return None


@dataclass
class TrendRule:
    """趋势报警：指标在连续 N 个窗口内持续上升/下降则触发。"""
    name: str
    point: str
    direction: str = "rising"  # "rising" | "falling"
    window_count: int = 5
    min_change_pct: float = 5.0  # 相对变化阈值（百分比）
    severity: str = "warning"

    def __post_init__(self):
        self._history: dict[str, list[float]] = {}

    def evaluate(self, ts_ms: int, asset_id: str, telemetry: dict[str, float]) -> AlarmEvent | None:
        val = telemetry.get(self.point)
        if val is None:
            return None

        key = asset_id
        if key not in self._history:
            self._history[key] = []
        hist = self._history[key]
        hist.append(val)
        if len(hist) > self.window_count:
            hist.pop(0)

        if len(hist) < self.window_count:
            return None

        first = hist[0]
        last = hist[-1]
        if first == 0:
            return None

        change_pct = ((last - first) / abs(first)) * 100

        triggered = False
        if self.direction == "rising" and change_pct > self.min_change_pct:
            triggered = True
        elif self.direction == "falling" and change_pct < -self.min_change_pct:
            triggered = True

        if triggered:
            direction_text = "持续上升" if self.direction == "rising" else "持续下降"
            msg = f"{self.point} {direction_text}: {change_pct:+.1f}% ({self.window_count} 窗口内)"
            return AlarmEvent(
                ts_ms=ts_ms,
                asset_id=asset_id,
                rule_name=self.name,
                rule_type="trend",
                severity=self.severity,
                message=msg,
            )
        return None


@dataclass
class CombinationRule:
    """组合规则：多个条件同时满足时触发。"""
    name: str
    conditions: list[dict]   # [{"point": "vib_rms", "op": ">", "threshold": 3.0}, ...]
    logic: str = "AND"       # "AND" | "OR"
    severity: str = "critical"

    def evaluate(self, ts_ms: int, asset_id: str, telemetry: dict[str, float]) -> AlarmEvent | None:
        results = []
        for cond in self.conditions:
            val = telemetry.get(cond["point"])
            if val is None:
                results.append(False)
                continue
            op = cond["op"]
            thr = cond["threshold"]
            if op == ">":
                results.append(val > thr)
            elif op == "<":
                results.append(val < thr)
            elif op == ">=":
                results.append(val >= thr)
            elif op == "<=":
                results.append(val <= thr)
            else:
                results.append(False)

        if self.logic == "AND":
            triggered = all(results)
        else:
            triggered = any(results)

        if triggered:
            cond_strs = [f"{c['point']}{c['op']}{c['threshold']}" for c in self.conditions]
            vals_strs = [f"{c['point']}={telemetry.get(c['point'], '?')}" for c in self.conditions]
            msg = f"组合规则触发 ({self.logic}): {', '.join(cond_strs)}; 当前: {', '.join(vals_strs)}"
            return AlarmEvent(
                ts_ms=ts_ms,
                asset_id=asset_id,
                rule_name=self.name,
                rule_type="combination",
                severity=self.severity,
                message=msg,
            )
        return None


@dataclass
class AlarmEngine:
    """报警规则引擎：聚合阈值、趋势、组合规则。"""
    rules: list = field(default_factory=list)

    def add_threshold(self, name: str, point: str, op: str, threshold: float, severity: str = "warning") -> AlarmEngine:
        self.rules.append(ThresholdRule(name=name, point=point, op=op, threshold=threshold, severity=severity))
        return self

    def add_trend(self, name: str, point: str, direction: str = "rising", window_count: int = 5,
                  min_change_pct: float = 5.0, severity: str = "warning") -> AlarmEngine:
        self.rules.append(TrendRule(name=name, point=point, direction=direction,
                                     window_count=window_count, min_change_pct=min_change_pct, severity=severity))
        return self

    def add_combination(self, name: str, conditions: list[dict], logic: str = "AND",
                        severity: str = "critical") -> AlarmEngine:
        self.rules.append(CombinationRule(name=name, conditions=conditions, logic=logic, severity=severity))
        return self

    def evaluate(self, ts_ms: int, asset_id: str, telemetry: dict[str, float]) -> list[AlarmEvent]:
        results: list[AlarmEvent] = []
        for rule in self.rules:
            evt = rule.evaluate(ts_ms, asset_id, telemetry)
            if evt is not None:
                results.append(evt)
        return results


def build_default_alarm_engine() -> AlarmEngine:
    """构建默认报警规则集：适用于旋转设备（泵/电机）。

    规则来源：
    - ISO 10816 振动标准：小型泵振动 RMS > 4.5 mm/s 为警告，> 7.1 为危险
    - 电机绝缘等级 (Class F): 绕组温度 > 105°C 需警告，> 130°C 需停机
    - 电机过载：额定电流超过 120% 触发警告
    """
    engine = AlarmEngine()

    # ── 阈值规则 ──
    engine.add_threshold("振动过高", "vib_rms", ">", 4.5, "warning")
    engine.add_threshold("振动严重超标", "vib_rms", ">", 7.1, "critical")
    engine.add_threshold("温度偏高", "temp_c", ">", 85.0, "warning")
    engine.add_threshold("温度严重偏高", "temp_c", ">", 105.0, "critical")
    engine.add_threshold("电流偏大", "motor_current_a", ">", 12.0, "warning")
    engine.add_threshold("电流严重过大", "motor_current_a", ">", 15.0, "critical")
    engine.add_threshold("转速异常偏低", "rpm", "<", 1000.0, "warning")

    # ── 趋势规则 ──
    engine.add_trend("振动持续上升", "vib_rms", "rising", window_count=5, min_change_pct=10.0, severity="warning")
    engine.add_trend("温度持续上升", "temp_c", "rising", window_count=5, min_change_pct=5.0, severity="warning")

    # ── 组合规则 ──
    engine.add_combination(
        "高温+高振动",
        [
            {"point": "temp_c", "op": ">", "threshold": 75.0},
            {"point": "vib_rms", "op": ">", "threshold": 3.5},
        ],
        logic="AND",
        severity="critical",
    )
    engine.add_combination(
        "高温+大电流",
        [
            {"point": "temp_c", "op": ">", "threshold": 80.0},
            {"point": "motor_current_a", "op": ">", "threshold": 10.0},
        ],
        logic="AND",
        severity="critical",
    )

    return engine
