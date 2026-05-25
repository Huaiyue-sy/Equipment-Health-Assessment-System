#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import time

from ihealthsim.sim.device import DeviceSimConfig, DeviceSimulator


def generate_raw_csv(
    *,
    out_csv: str,
    seconds: int,
    asset_id: str,
    sample_period_s: float,
    ambient_temp_c: float,
    degradation_per_hour: float,
    fault_inject_at_s: int,
    seed: int,
    start_ts_ms: int | None,
) -> str:
    os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)

    cfg = DeviceSimConfig(
        asset_id=asset_id,
        ambient_temp_c=ambient_temp_c,
        sample_period_s=sample_period_s,
        degradation_per_hour=degradation_per_hour,
        fault_inject_at_s=fault_inject_at_s,
    )
    sim = DeviceSimulator(cfg, seed=seed)

    if start_ts_ms is None:
        start_ts_ms = int(time.time() * 1000)

    fieldnames = ["ts_ms", "asset_id", "point", "value", "quality"]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()

        step_ms = int(sample_period_s * 1000)
        for i in range(seconds):
            ts_ms = start_ts_ms + i * step_ms
            for p in sim.step(ts_ms):
                w.writerow(
                    {
                        "ts_ms": p.ts_ms,
                        "asset_id": p.asset_id,
                        "point": p.point,
                        "value": p.value,
                        "quality": p.quality,
                    }
                )

    return out_csv


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate simulated industrial device telemetry to raw CSV.")
    ap.add_argument("--out", type=str, default="data/raw.csv", help="output CSV path")
    ap.add_argument("--seconds", type=int, default=3600, help="simulation duration in seconds")
    ap.add_argument("--asset-id", type=str, default="PUMP-001")
    ap.add_argument("--sample-period-s", type=float, default=1.0)

    ap.add_argument("--ambient-temp-c", type=float, default=25.0)
    ap.add_argument("--degradation-per-hour", type=float, default=0.03)
    ap.add_argument("--fault-inject-at-s", type=int, default=3600)

    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--start-ts-ms",
        type=int,
        default=None,
        help="optional start timestamp in ms; default uses current time",
    )

    args = ap.parse_args()

    out = generate_raw_csv(
        out_csv=args.out,
        seconds=args.seconds,
        asset_id=args.asset_id,
        sample_period_s=args.sample_period_s,
        ambient_temp_c=args.ambient_temp_c,
        degradation_per_hour=args.degradation_per_hour,
        fault_inject_at_s=args.fault_inject_at_s,
        seed=args.seed,
        start_ts_ms=args.start_ts_ms,
    )

    print(f"OK: wrote {out}")
    print("Next:")
    print("  /Users/huyuuu/gatewayFail/.venv/bin/python -m ihealthsim.cli make-features")
    print("  /Users/huyuuu/gatewayFail/.venv/bin/python -m ihealthsim.cli train")


if __name__ == "__main__":
    main()
