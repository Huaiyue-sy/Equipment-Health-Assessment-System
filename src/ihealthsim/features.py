from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FeatureConfig:
    window_s: int = 60


def _p95(x: pd.Series) -> float:
    return float(np.nanpercentile(x.to_numpy(dtype=float), 95))


def _slope(ts_ms: pd.Series, x: pd.Series) -> float:
    # 简单线性回归斜率（每秒变化量）
    t = (ts_ms.to_numpy(dtype=float) - float(ts_ms.iloc[0])) / 1000.0
    y = x.to_numpy(dtype=float)
    if len(y) < 2 or np.allclose(t, t[0]):
        return 0.0
    # polyfit 可能在 NaN 时出问题
    mask = np.isfinite(t) & np.isfinite(y)
    if mask.sum() < 2:
        return 0.0
    a, _b = np.polyfit(t[mask], y[mask], deg=1)
    return float(a)


def make_features(raw_csv: str, out_csv: str, *, cfg: FeatureConfig = FeatureConfig()) -> str:
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)

    raw = pd.read_csv(raw_csv)
    raw["ts_ms"] = raw["ts_ms"].astype("int64")

    # long -> wide
    wide = raw.pivot_table(index=["ts_ms", "asset_id"], columns="point", values="value", aggfunc="last").reset_index()
    wide = wide.sort_values(["asset_id", "ts_ms"]).reset_index(drop=True)

    # 窗口分组
    window_ms = cfg.window_s * 1000
    wide["window_start_ms"] = (wide["ts_ms"] // window_ms) * window_ms

    numeric_points = [c for c in wide.columns if c not in {"ts_ms", "asset_id", "window_start_ms"}]

    agg = {}
    for c in numeric_points:
        agg[f"{c}_mean"] = (c, "mean")
        agg[f"{c}_std"] = (c, "std")
        agg[f"{c}_min"] = (c, "min")
        agg[f"{c}_max"] = (c, "max")
        agg[f"{c}_p95"] = (c, _p95)

    # 基础统计
    g = wide.groupby(["asset_id", "window_start_ms"], sort=False)
    feat = g.agg(**agg).reset_index()

    # slope（趋势）：对关键点位计算
    for base in ["temp_c", "vib_rms", "motor_current_a"]:
        if base in wide.columns:
            feat[f"{base}_slope"] = g.apply(lambda df: _slope(df["ts_ms"], df[base]), include_groups=False).to_numpy()

    # delta：与上一窗口的均值差
    for base in ["temp_c", "vib_rms", "motor_current_a", "rpm"]:
        col = f"{base}_mean"
        if col in feat.columns:
            feat[f"{base}_delta"] = feat.groupby("asset_id")[col].diff().fillna(0.0)

    # 工况归一化示例：振动按转速归一化
    if "vib_rms_mean" in feat.columns and "rpm_mean" in feat.columns:
        feat["vib_rms_norm"] = feat["vib_rms_mean"] / (feat["rpm_mean"] / 1000.0 + 1e-6)

    # 标签：窗口内取最大等级（最坏）
    if "label_health_level_mean" in feat.columns:
        feat["y"] = feat["label_health_level_mean"].round().clip(0, 3).astype(int)
    else:
        raise ValueError("raw 数据里缺少 label_health_level 点位，无法监督训练")

    feat.to_csv(out_csv, index=False)
    return out_csv
