from __future__ import annotations

import math
import random
from dataclasses import dataclass

import numpy as np

from ..schemas import TelemetryPoint


@dataclass
class DeviceSimConfig:
    asset_id: str = "PUMP-001"
    ambient_temp_c: float = 25.0
    rated_rpm: float = 2900.0
    sample_period_s: float = 1.0

    # 退化速度与故障注入
    degradation_per_hour: float = 0.03  # 越大越快
    fault_inject_at_s: int = 3600  # 1h 时开始显著恶化

    # 随机性控制
    degradation_std: float = 0.5  # 退化速度相对标准差 (0=完全均匀, 1=噪声与退化同量级)
    transient_prob_per_s: float = 0.0005  # 每秒出现瞬态尖峰的概率
    transient_magnitude: float = 2.5  # 瞬态尖峰的强度倍数


class DeviceSimulator:
    """模拟旋转设备的遥测：温度、振动RMS、电机电流、转速。

    latent_health: 1.0(好) -> 0.0(坏)
    label_health_level: 0..3（用来训练/评估，真实场景一般不可得）
    """

    def __init__(self, cfg: DeviceSimConfig, seed: int = 42) -> None:
        self.cfg = cfg
        self._rng = random.Random(seed)
        self._t_s = 0
        self._latent_health = 1.0

        # 每个实例独立随机化：
        # - 故障注入时间在配置值的 ±20% 范围内抖动
        jitter = int(cfg.fault_inject_at_s * 0.2 * (self._rng.random() * 2 - 1))
        self._fault_inject_at_s = max(0, cfg.fault_inject_at_s + jitter)

        # - 环境温度随时间缓慢漂移（半正弦波 + 随机噪声）
        self._ambient_phase = self._rng.random() * 2 * math.pi
        self._ambient_period_s = self._rng.uniform(600, 1800)  # 10-30分钟周期

        # - 当前工况阶段持续时间的随机偏移
        self._phase_period_s = int(self._rng.gauss(600, 60))  # 约10分钟，带随机变化
        self._phase_period_s = max(300, min(900, self._phase_period_s))

        # - 传感器基线漂移（每台设备安装时系统误差不同）
        self._vib_bias = self._rng.gauss(0, 0.05)
        self._temp_bias = self._rng.gauss(0, 0.3)
        self._cur_bias = self._rng.gauss(0, 0.15)

    def _operating_state(self) -> tuple[float, float]:
        """返回 (rpm, load)，带随机工况持续时间和瞬态扰动"""
        phase = (self._t_s // self._phase_period_s) % 6
        rpm = {
            0: 1500,
            1: 2000,
            2: 2600,
            3: 2900,
            4: 2400,
            5: 1800,
        }[phase]
        rpm += self._rng.gauss(0, 15)

        # 负载在基准值基础上叠加随机游走（模拟负载的缓慢变化）
        load_base = {
            0: 0.35,
            1: 0.55,
            2: 0.75,
            3: 0.85,
            4: 0.65,
            5: 0.45,
        }[phase]
        # 负载随机游走：每秒 ±0.005 以内的小幅漂移
        load_drift = 0.005 * math.sin(self._t_s * 0.05 + self._ambient_phase)
        load = load_base + load_drift + self._rng.gauss(0, 0.02)
        load = max(0.1, min(1.0, load))
        return rpm, load

    def _update_degradation(self) -> None:
        # 基础退化速度（每秒），加上高斯噪声模拟真实设备的不均匀退化
        per_s = self.cfg.degradation_per_hour / 3600.0
        noise_scale = per_s * self.cfg.degradation_std
        actual_per_s = max(0.0, self._rng.gauss(per_s, noise_scale))
        self._latent_health = max(0.0, self._latent_health - actual_per_s)

        # 故障注入后退化加速（3x 基础速度 + 噪声）
        if self._t_s >= self._fault_inject_at_s:
            accel = max(0.0, self._rng.gauss(3.0 * per_s, 1.5 * noise_scale))
            self._latent_health = max(0.0, self._latent_health - accel)

        # 偶尔的微小恢复（设备冷却、润滑改善等），概率约 5%/秒
        if self._rng.random() < 0.05:
            recovery = self._rng.uniform(0, 0.3 * per_s)
            self._latent_health = min(1.0, self._latent_health + recovery)

    def _health_level(self) -> int:
        h = self._latent_health
        if h >= 0.80:
            return 0
        if h >= 0.60:
            return 1
        if h >= 0.40:
            return 2
        return 3

    def _ambient_temp(self) -> float:
        """环境温度：缓慢正弦漂移 + 小幅随机波动"""
        drift = 3.0 * math.sin(2 * math.pi * self._t_s / self._ambient_period_s + self._ambient_phase)
        return self.cfg.ambient_temp_c + drift + self._rng.gauss(0, 0.2)

    def _transient_factor(self) -> float:
        """瞬态尖峰：偶尔出现的短暂异常值（如负载突变、异物进入等）"""
        if self._rng.random() < self.cfg.transient_prob_per_s:
            return self.cfg.transient_magnitude * self._rng.uniform(0.5, 1.5)
        return 0.0

    def step(self, ts_ms: int) -> list[TelemetryPoint]:
        self._update_degradation()
        rpm, load = self._operating_state()
        ambient = self._ambient_temp()

        # 信号合成：健康越差，振动/温度/电流偏离越大
        unfault = 1.0 - self._latent_health

        # 传感器噪声随退化加剧而增加（设备恶化时测量更不稳定）
        noise_scale = 1.0 + unfault * 2.0

        # 瞬态因子
        transient = self._transient_factor()

        # 振动RMS：与转速近似线性，同时受不平衡/轴承劣化影响
        vib_base = 1.2 + 0.00035 * rpm + self._vib_bias
        vib_fault = unfault * (5.0 + 0.002 * rpm)
        vib_rms = vib_base + vib_fault + self._rng.gauss(0, 0.08 * noise_scale)
        vib_rms += transient * vib_base  # 瞬态尖峰加在振动上

        # 温度：与负载相关，同时故障引起额外升温和漂移
        temp_base = ambient + 25.0 * load + self._temp_bias
        temp_fault = unfault * (30.0 + 15.0 * load)
        temp_c = temp_base + temp_fault + self._rng.gauss(0, 0.4 * noise_scale)

        # 电流：与负载相关，故障（摩擦/效率降低）会让电流升高
        cur_base = 10.0 + 25.0 * load + self._cur_bias
        cur_fault = unfault * (18.0 + 12.0 * load)
        motor_current_a = cur_base + cur_fault + self._rng.gauss(0, 0.25 * noise_scale)
        motor_current_a += transient * cur_base * 0.3

        # 生成点位
        asset = self.cfg.asset_id
        label = float(self._health_level())

        points = [
            TelemetryPoint(ts_ms=ts_ms, asset_id=asset, point="rpm", value=float(rpm)),
            TelemetryPoint(ts_ms=ts_ms, asset_id=asset, point="load", value=float(load)),
            TelemetryPoint(ts_ms=ts_ms, asset_id=asset, point="vib_rms", value=float(vib_rms)),
            TelemetryPoint(ts_ms=ts_ms, asset_id=asset, point="temp_c", value=float(temp_c)),
            TelemetryPoint(ts_ms=ts_ms, asset_id=asset, point="motor_current_a", value=float(motor_current_a)),
            TelemetryPoint(ts_ms=ts_ms, asset_id=asset, point="label_health_level", value=label),
        ]

        self._t_s += int(self.cfg.sample_period_s)
        return points
