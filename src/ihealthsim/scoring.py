from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass

import joblib
import numpy as np
import pandas as pd
from sklearn.tree import _tree

from .alarm import AlarmEngine, build_default_alarm_engine
from .schemas import AlarmEvent, HealthResult, TelemetryPoint


@dataclass
class DebounceConfig:
    abnormal_level: int = 2
    severe_level: int = 3
    raise_n: int = 3
    recover_n: int = 5


class OnlineScorer:
    def __init__(self, model_path: str, *, window_s: int = 60, debounce: DebounceConfig | None = None,
                 alarm_engine: AlarmEngine | None = None) -> None:
        bundle = joblib.load(model_path)
        self.pipe = bundle["pipeline"]
        self.feature_cols: list[str] = list(bundle["feature_cols"])
        self.model_type: str = bundle.get("model_type", "tree")
        self.feature_importance: list[list] = bundle.get("feature_importance", [])
        self.feature_stats: dict[int, dict[str, tuple[float, float]]] = bundle.get("feature_stats", {})
        self.window_s = window_s
        self.debounce = debounce or DebounceConfig()
        self.alarm_engine = alarm_engine or build_default_alarm_engine()

        # 每个 asset 缓冲最近窗口的数据
        self._buf: dict[str, deque[TelemetryPoint]] = defaultdict(lambda: deque(maxlen=200_000))
        self._last_emit_level: dict[str, int] = defaultdict(int)
        self._streak: dict[str, int] = defaultdict(int)
        self._latest: dict[str, HealthResult] = {}
        self._latest_alarms: dict[str, list[AlarmEvent]] = defaultdict(list)
        # 防抖：每个 asset 最小评分间隔 (ms)
        self._last_score_ms: dict[str, int] = defaultdict(int)

    def reset(self, asset_id: str | None = None) -> None:
        """重置内部状态，支持单个资产或全部资产。"""
        if asset_id is not None:
            self._buf.pop(asset_id, None)
            self._last_emit_level.pop(asset_id, None)
            self._streak.pop(asset_id, None)
            self._latest.pop(asset_id, None)
            self._latest_alarms.pop(asset_id, None)
            self._last_score_ms.pop(asset_id, None)
        else:
            self._buf.clear()
            self._last_emit_level.clear()
            self._streak.clear()
            self._latest.clear()
            self._latest_alarms.clear()
            self._last_score_ms.clear()

    def latest(self, asset_id: str) -> HealthResult | None:
        return self._latest.get(asset_id)

    def latest_alarms(self, asset_id: str) -> list[AlarmEvent]:
        return self._latest_alarms.get(asset_id, [])

    def ingest(self, p: TelemetryPoint) -> HealthResult | None:
        self._buf[p.asset_id].append(p)

        # 防抖：每个 asset 最小 500ms 间隔评分一次
        min_interval_ms = 500
        last_ms = self._last_score_ms.get(p.asset_id, 0)
        if p.ts_ms - last_ms < min_interval_ms:
            return None
        self._last_score_ms[p.asset_id] = p.ts_ms

        window_ms = self.window_s * 1000
        window_start = (p.ts_ms // window_ms) * window_ms
        window_end = window_start + window_ms

        # 取出该窗口内数据
        pts = [x for x in self._buf[p.asset_id] if window_start <= x.ts_ms < window_end]
        if len(pts) < 20:
            return None

        df = pd.DataFrame([{ "ts_ms": x.ts_ms, "asset_id": x.asset_id, "point": x.point, "value": x.value } for x in pts])
        wide = df.pivot_table(index=["ts_ms", "asset_id"], columns="point", values="value", aggfunc="last").reset_index()
        wide = wide.sort_values(["asset_id", "ts_ms"]).reset_index(drop=True)

        # 简化版特征（与离线 features.py 一致的核心子集）
        feat = {
            "rpm_mean": float(wide.get("rpm", pd.Series(dtype=float)).mean()),
            "load_mean": float(wide.get("load", pd.Series(dtype=float)).mean()),
            "vib_rms_mean": float(wide.get("vib_rms", pd.Series(dtype=float)).mean()),
            "temp_c_mean": float(wide.get("temp_c", pd.Series(dtype=float)).mean()),
            "motor_current_a_mean": float(wide.get("motor_current_a", pd.Series(dtype=float)).mean()),
            "vib_rms_std": float(wide.get("vib_rms", pd.Series(dtype=float)).std()),
            "temp_c_std": float(wide.get("temp_c", pd.Series(dtype=float)).std()),
        }
        if np.isfinite(feat["vib_rms_mean"]) and np.isfinite(feat["rpm_mean"]):
            feat["vib_rms_norm"] = feat["vib_rms_mean"] / (feat["rpm_mean"] / 1000.0 + 1e-6)

        x = pd.DataFrame([{c: feat.get(c, np.nan) for c in self.feature_cols}])
        proba = self.pipe.predict_proba(x)[0].tolist()
        level = int(self.pipe.predict(x)[0])

        # 去抖/迟滞：基于 level
        last = self._last_emit_level[p.asset_id]
        target = level

        if target > last:
            self._streak[p.asset_id] = self._streak[p.asset_id] + 1
            if self._streak[p.asset_id] >= self.debounce.raise_n:
                last = target
                self._streak[p.asset_id] = 0
        elif target < last:
            self._streak[p.asset_id] = self._streak[p.asset_id] + 1
            if self._streak[p.asset_id] >= self.debounce.recover_n:
                last = target
                self._streak[p.asset_id] = 0
        else:
            self._streak[p.asset_id] = 0

        self._last_emit_level[p.asset_id] = last

        score = float(100.0 - (last / 3.0) * 100.0)
        explanation = self._explain(x)

        # 提取实际遥测值供报警评估
        telemetry_snapshot = {
            "vib_rms": float(wide.get("vib_rms", pd.Series(dtype=float)).mean()) if "vib_rms" in wide.columns else None,
            "temp_c": float(wide.get("temp_c", pd.Series(dtype=float)).mean()) if "temp_c" in wide.columns else None,
            "motor_current_a": float(wide.get("motor_current_a", pd.Series(dtype=float)).mean()) if "motor_current_a" in wide.columns else None,
            "rpm": float(wide.get("rpm", pd.Series(dtype=float)).mean()) if "rpm" in wide.columns else None,
        }

        hr = HealthResult(
            ts_ms=window_end - 1,
            asset_id=p.asset_id,
            health_level=last,
            health_score=score,
            proba=proba,
            explanation=explanation,
            telemetry=telemetry_snapshot,
        )
        self._latest[p.asset_id] = hr

        # 运行报警规则引擎
        alarms = self.alarm_engine.evaluate(window_end - 1, p.asset_id, telemetry_snapshot)
        if alarms:
            self._latest_alarms[p.asset_id] = alarms

        return hr

    def _explain(self, x_df: pd.DataFrame) -> str:
        """根据模型类型生成解释路径。"""
        if self.model_type == "tree":
            return self._explain_tree_path(x_df)
        else:
            return self._explain_feature_importance(x_df)

    def _explain_tree_path(self, x_df: pd.DataFrame) -> str:
        """决策树：输出完整决策路径。"""
        try:
            pre = self.pipe.named_steps["pre"]
            clf = self.pipe.named_steps["clf"]
            x = pre.transform(x_df)
            tree = clf.tree_
            feature_names = self.feature_cols

            node = 0
            parts: list[str] = []
            while tree.feature[node] != _tree.TREE_UNDEFINED:
                fid = tree.feature[node]
                thr = tree.threshold[node]
                fname = feature_names[fid] if fid < len(feature_names) else f"f{fid}"
                val = float(x[0, fid])
                if val <= thr:
                    parts.append(f"{fname} <= {thr:.3f} (val={val:.3f})")
                    node = tree.children_left[node]
                else:
                    parts.append(f"{fname} > {thr:.3f} (val={val:.3f})")
                    node = tree.children_right[node]
                if len(parts) >= 12:
                    break
            return " -> ".join(parts)
        except Exception:
            return self._explain_feature_importance(x_df)

    def _explain_feature_importance(self, x_df: pd.DataFrame) -> str:
        """XGBoost/LightGBM：用特征重要性 + 与健康基线 (Lv0) 偏差生成诊断解释。"""
        if not self.feature_importance:
            return "model prediction (no explanation available)"

        pre = self.pipe.named_steps["pre"]
        x_transformed = pre.transform(x_df)
        row = {c: float(x_transformed[0, i]) for i, c in enumerate(self.feature_cols)}

        # 取 Lv0（健康）的特征统计作为基线
        baseline = self.feature_stats.get(0, {})

        parts = []
        for fname, imp in self.feature_importance[:6]:
            val = row.get(fname, float("nan"))
            stats = baseline.get(fname)
            if stats is not None and np.isfinite(val):
                mean, std = stats
                z = (val - mean) / std
                if z > 2.0:
                    direction = "偏高↑"
                elif z > 1.0:
                    direction = "略高"
                elif z < -2.0:
                    direction = "偏低↓"
                elif z < -1.0:
                    direction = "略低"
                else:
                    direction = "正常"
                parts.append(f"{fname}>{direction}(val={val:.3f}, z={z:+.1f}, imp={imp:.4f})")
            else:
                parts.append(f"{fname}={val:.3f}(imp={imp:.4f})")
        return " -> ".join(parts)
