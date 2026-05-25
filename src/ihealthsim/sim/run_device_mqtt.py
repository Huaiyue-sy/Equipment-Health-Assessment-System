from __future__ import annotations

import time

from ..mqtt_transport import MqttConfig, dumps_payload, make_client, topic_for_asset
from .device import DeviceSimConfig, DeviceSimulator


def publish_device(
    *,
    mqtt_cfg: MqttConfig,
    sim_cfg: DeviceSimConfig,
    seconds: int,
    sleep_s: float = 0.0,
) -> None:
    """将模拟设备遥测发布到 MQTT（EMQX）。

    sleep_s:
      - 0.0: 加速仿真（尽可能快）
      - 1.0: 近似实时（每秒一批点位）
    """

    sim = DeviceSimulator(sim_cfg)
    client = make_client(client_id=f"sim-pub-{sim_cfg.asset_id}", cfg=mqtt_cfg)
    client.loop_start()

    start_ms = int(time.time() * 1000)
    topic = topic_for_asset(mqtt_cfg, sim_cfg.asset_id)

    for i in range(seconds):
        ts_ms = start_ms + i * int(sim_cfg.sample_period_s * 1000)
        for p in sim.step(ts_ms):
            payload = {
                "ts_ms": p.ts_ms,
                "asset_id": p.asset_id,
                "point": p.point,
                "value": p.value,
                "quality": p.quality,
            }
            client.publish(topic, dumps_payload(payload), qos=0, retain=False)
        if sleep_s > 0:
            time.sleep(sleep_s)

    client.loop_stop()
    client.disconnect()
