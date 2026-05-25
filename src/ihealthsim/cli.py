from __future__ import annotations

import argparse
import os
import threading
import time

from rich.console import Console

from .api import create_app
from .features import FeatureConfig, make_features
from .mqtt_collector import MqttCsvCollector
from .mqtt_ingest import start_ingest
from .mqtt_live import live_score
from .mqtt_transport import MqttConfig
from .scoring import OnlineScorer
from .sim.device import DeviceSimConfig
from .sim.run_device_mqtt import publish_device
from .train import TrainConfig, train_tree


console = Console()


def _paths() -> dict[str, str]:
    return {
        "raw": os.path.join("data", "raw.csv"),
        "features": os.path.join("data", "features.csv"),
        "model": os.path.join("models", "tree.joblib"),
    }


async def _generate_data(seconds: int) -> None:
    raise RuntimeError("已改为 MQTT(EMQX) 模式：请使用 generate-data-mqtt / pub-device / collect")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="ihealthsim")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_mqtt_args(pp: argparse.ArgumentParser) -> None:
        pp.add_argument("--mqtt-host", type=str, default="127.0.0.1")
        pp.add_argument("--mqtt-port", type=int, default=1883)
        pp.add_argument("--mqtt-username", type=str, default=None)
        pp.add_argument("--mqtt-password", type=str, default=None)
        pp.add_argument("--mqtt-base-topic", type=str, default="telemetry/raw")

    p_demo = sub.add_parser("demo", help="端到端：生成数据->特征->训练->在线打分")
    p_demo.add_argument("--train-seconds", type=int, default=7200)
    p_demo.add_argument("--live-seconds", type=int, default=600)
    p_demo.add_argument("--sleep-s", type=float, default=0.0, help="发布端每秒 sleep，0 表示加速仿真")
    p_demo.add_argument("--asset-id", type=str, default="PUMP-001")
    p_demo.add_argument("--fault-inject-at-s", type=int, default=1200)
    p_demo.add_argument("--degradation-per-hour", type=float, default=0.06)
    p_demo.add_argument("--ambient-temp-c", type=float, default=25.0)
    p_demo.add_argument("--duration-s", type=float, default=None, help="采集超时时间；默认按 seconds/sleep 自动估算")
    p_demo.add_argument("--max-depth", type=int, default=5)
    p_demo.add_argument("--min-samples-leaf", type=int, default=10)
    p_demo.add_argument("--feature-set", type=str, choices=["online", "all"], default="online")
    p_demo.add_argument("--model", type=str, choices=["tree", "xgb", "lgb"], default="tree")
    add_mqtt_args(p_demo)

    p_pub = sub.add_parser("pub-device", help="发布模拟设备遥测到 MQTT(EMQX)")
    p_pub.add_argument("--seconds", type=int, default=600)
    p_pub.add_argument("--sleep-s", type=float, default=0.0)
    p_pub.add_argument("--asset-id", type=str, default="PUMP-001")
    p_pub.add_argument("--fault-inject-at-s", type=int, default=3600)
    p_pub.add_argument("--degradation-per-hour", type=float, default=0.03)
    p_pub.add_argument("--ambient-temp-c", type=float, default=25.0)
    add_mqtt_args(p_pub)

    p_collect = sub.add_parser("collect", help="从 MQTT(EMQX) 订阅采集并落盘 raw.csv")
    p_collect.add_argument("--duration-s", type=float, default=30.0)
    p_collect.add_argument("--max-messages", type=int, default=None)
    p_collect.add_argument("--topic-filter", type=str, default="telemetry/raw/#")
    add_mqtt_args(p_collect)

    p_gen = sub.add_parser("generate-data-mqtt", help="同进程：采集 + 发布（通过 EMQX）生成 raw.csv")
    p_gen.add_argument("--seconds", type=int, default=3600)
    p_gen.add_argument("--sleep-s", type=float, default=0.0)
    p_gen.add_argument("--duration-s", type=float, default=None, help="采集超时时间；默认按 seconds/sleep 自动估算")
    p_gen.add_argument("--asset-id", type=str, default="PUMP-001")
    p_gen.add_argument("--fault-inject-at-s", type=int, default=3600)
    p_gen.add_argument("--degradation-per-hour", type=float, default=0.03)
    p_gen.add_argument("--ambient-temp-c", type=float, default=25.0)
    add_mqtt_args(p_gen)

    p_feat = sub.add_parser("make-features", help="从 raw.csv 生成窗口特征")

    p_train = sub.add_parser("train", help="训练决策树并保存模型")
    p_train.add_argument("--max-depth", type=int, default=5)
    p_train.add_argument("--min-samples-leaf", type=int, default=50)
    p_train.add_argument("--feature-set", type=str, choices=["online", "all"], default="online")
    p_train.add_argument("--test-size", type=float, default=0.3)
    p_train.add_argument("--model", type=str, choices=["tree", "xgb", "lgb"], default="tree",
                         help="模型类型: tree (决策树), xgb (XGBoost), lgb (LightGBM)")

    p_live = sub.add_parser("live", help="订阅 MQTT 在线打分输出（可选同时发布模拟设备）")
    p_live.add_argument("--duration-s", type=float, default=60.0)
    p_live.add_argument("--topic-filter", type=str, default="telemetry/raw/#")
    p_live.add_argument("--simulate-seconds", type=int, default=0, help=">0 时同时发布模拟设备")
    p_live.add_argument("--sleep-s", type=float, default=0.0)
    p_live.add_argument("--asset-id", type=str, default="PUMP-001")
    p_live.add_argument("--fault-inject-at-s", type=int, default=3600)
    p_live.add_argument("--degradation-per-hour", type=float, default=0.03)
    p_live.add_argument("--ambient-temp-c", type=float, default=25.0)
    add_mqtt_args(p_live)

    p_serve = sub.add_parser("serve", help="启动 API")
    p_serve.add_argument("--host", type=str, default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--topic-filter", type=str, default="telemetry/raw/#")
    add_mqtt_args(p_serve)

    args = p.parse_args(argv)
    paths = _paths()

    mqtt_cfg = None
    if hasattr(args, "mqtt_host"):
        mqtt_cfg = MqttConfig(
            host=args.mqtt_host,
            port=args.mqtt_port,
            username=args.mqtt_username,
            password=args.mqtt_password,
            base_topic=args.mqtt_base_topic,
        )

    if args.cmd == "pub-device":
        sim_cfg = DeviceSimConfig(
            asset_id=args.asset_id,
            fault_inject_at_s=args.fault_inject_at_s,
            degradation_per_hour=args.degradation_per_hour,
            ambient_temp_c=args.ambient_temp_c,
        )
        console.print(f"发布模拟设备 -> MQTT topic={mqtt_cfg.base_topic}/{sim_cfg.asset_id}")
        publish_device(mqtt_cfg=mqtt_cfg, sim_cfg=sim_cfg, seconds=args.seconds, sleep_s=args.sleep_s)
        return

    if args.cmd == "collect":
        console.print(f"采集 MQTT -> {paths['raw']}")
        collector = MqttCsvCollector(paths["raw"])
        try:
            n = collector.collect(
                mqtt_cfg=mqtt_cfg,
                topic_filter=args.topic_filter,
                duration_s=args.duration_s,
                max_messages=args.max_messages,
            )
            console.print(f"采集完成: {n} messages")
        finally:
            collector.close()
        return

    if args.cmd == "generate-data-mqtt":
        # 预计每秒 6 点位
        expected = args.seconds * 6
        collector = MqttCsvCollector(paths["raw"])

        # 自动估算采集超时时间：
        # - 加速仿真(sleep=0)：给一个保守的 20s 基准 + 少量余量
        # - 近实时(sleep>0)：按 seconds*sleep + 10s
        if args.duration_s is None:
            if args.sleep_s and args.sleep_s > 0:
                duration_s = float(args.seconds) * float(args.sleep_s) + 10.0
            else:
                duration_s = 20.0
        else:
            duration_s = float(args.duration_s)

        def collect_thread():
            collector.collect(
                mqtt_cfg=mqtt_cfg,
                topic_filter=f"{mqtt_cfg.base_topic}/#",
                duration_s=duration_s,
                max_messages=expected,
            )

        t = threading.Thread(target=collect_thread, daemon=True)
        t.start()
        time.sleep(0.3)

        sim_cfg = DeviceSimConfig(
            asset_id=args.asset_id,
            fault_inject_at_s=args.fault_inject_at_s,
            degradation_per_hour=args.degradation_per_hour,
            ambient_temp_c=args.ambient_temp_c,
        )
        console.print(f"发布模拟设备 {args.seconds}s，并采集落盘")
        try:
            publish_device(mqtt_cfg=mqtt_cfg, sim_cfg=sim_cfg, seconds=args.seconds, sleep_s=args.sleep_s)
            t.join(timeout=max(3.0, duration_s + 2.0))
        finally:
            collector.close()
        console.print(f"raw 已生成: {paths['raw']} (collected={collector.count}/{expected})")
        if collector.count < expected:
            console.print("[yellow]WARNING[/yellow]: 采集数量不足，可能是 EMQX 未启动/ACL 拒绝/topic 不匹配/超时过短。")
        return

    if args.cmd == "make-features":
        console.print(f"提取特征: {paths['features']}")
        make_features(paths["raw"], paths["features"], cfg=FeatureConfig(window_s=60))
        return

    if args.cmd == "train":
        console.print(f"训练模型 -> {paths['model']}")
        cfg = TrainConfig(max_depth=args.max_depth, min_samples_leaf=args.min_samples_leaf, feature_set=args.feature_set, test_size=args.test_size, model_type=args.model)
        train_tree(paths["features"], paths["model"], cfg=cfg)
        return

    if args.cmd == "live":
        console.print(f"订阅 MQTT 在线打分: 使用模型 {paths['model']}")
        scorer = OnlineScorer(paths["model"], window_s=60)

        pub_t = None
        if args.simulate_seconds and args.simulate_seconds > 0:
            sim_cfg = DeviceSimConfig(
                asset_id=args.asset_id,
                fault_inject_at_s=args.fault_inject_at_s,
                degradation_per_hour=args.degradation_per_hour,
                ambient_temp_c=args.ambient_temp_c,
            )

            def pub_thread():
                publish_device(mqtt_cfg=mqtt_cfg, sim_cfg=sim_cfg, seconds=args.simulate_seconds, sleep_s=args.sleep_s)

            pub_t = threading.Thread(target=pub_thread, daemon=True)
            pub_t.start()

        def on_result(hr):
            console.print(
                f"[bold]asset={hr.asset_id}[/bold] level={hr.health_level} score={hr.health_score:.1f} proba={list(map(lambda x: round(x,3), hr.proba))}"
            )
            console.print(f"  path: {hr.explanation}\n")

        live_score(
            mqtt_cfg=mqtt_cfg,
            scorer=scorer,
            topic_filter=args.topic_filter,
            duration_s=args.duration_s,
            on_result=on_result,
        )
        if pub_t is not None:
            pub_t.join(timeout=1.0)
        return

    if args.cmd == "serve":
        from uvicorn import run

        scorer = OnlineScorer(paths["model"], window_s=60)
        stop = start_ingest(mqtt_cfg=mqtt_cfg, scorer=scorer, topic_filter=args.topic_filter)
        app = create_app(scorer)
        try:
            run(app, host=args.host, port=args.port)
        finally:
            stop()
        return

    if args.cmd == "demo":
        console.print("Step1) 通过 EMQX 生成训练数据 (raw.csv)")
        expected = args.train_seconds * 6
        collector = MqttCsvCollector(paths["raw"])

        if args.duration_s is None:
            if args.sleep_s and args.sleep_s > 0:
                duration_s = float(args.train_seconds) * float(args.sleep_s) + 10.0
            else:
                duration_s = 20.0
        else:
            duration_s = float(args.duration_s)

        def collect_thread():
            collector.collect(
                mqtt_cfg=mqtt_cfg,
                topic_filter=f"{mqtt_cfg.base_topic}/#",
                duration_s=duration_s,
                max_messages=expected,
            )

        t = threading.Thread(target=collect_thread, daemon=True)
        t.start()
        time.sleep(0.3)
        try:
            publish_device(
                mqtt_cfg=mqtt_cfg,
                sim_cfg=DeviceSimConfig(
                    asset_id=args.asset_id,
                    fault_inject_at_s=args.fault_inject_at_s,
                    degradation_per_hour=args.degradation_per_hour,
                    ambient_temp_c=args.ambient_temp_c,
                ),
                seconds=args.train_seconds,
                sleep_s=args.sleep_s,
            )
            t.join(timeout=max(3.0, duration_s + 2.0))
        finally:
            collector.close()
        console.print(f"采集统计: {collector.count}/{expected}")
        if collector.count < expected:
            console.print("[yellow]WARNING[/yellow]: 训练数据采集数量不足，后续训练可能失败或效果很差。")

        console.print("Step2) 特征提取")
        make_features(paths["raw"], paths["features"], cfg=FeatureConfig(window_s=60))

        console.print(f"Step3) 训练模型 ({args.model})")
        train_tree(
            paths["features"],
            paths["model"],
            cfg=TrainConfig(max_depth=args.max_depth, min_samples_leaf=args.min_samples_leaf, feature_set=args.feature_set, model_type=args.model),
        )

        console.print("Step4) 在线仿真打分输出（订阅 EMQX，同时发布模拟设备）")
        scorer = OnlineScorer(paths["model"], window_s=60)

        def pub_thread():
            publish_device(
                mqtt_cfg=mqtt_cfg,
                sim_cfg=DeviceSimConfig(
                    asset_id=args.asset_id,
                    fault_inject_at_s=args.fault_inject_at_s,
                    degradation_per_hour=args.degradation_per_hour,
                    ambient_temp_c=args.ambient_temp_c,
                ),
                seconds=args.live_seconds,
                sleep_s=args.sleep_s,
            )

        pub_t = threading.Thread(target=pub_thread, daemon=True)
        pub_t.start()

        def on_result(hr):
            console.print(
                f"[bold]asset={hr.asset_id}[/bold] level={hr.health_level} score={hr.health_score:.1f} proba={list(map(lambda x: round(x,3), hr.proba))}"
            )
            console.print(f"  path: {hr.explanation}\n")

        live_score(
            mqtt_cfg=mqtt_cfg,
            scorer=scorer,
            topic_filter=f"{mqtt_cfg.base_topic}/#",
            duration_s=max(10.0, float(args.live_seconds) * 0.2 + 5.0),
            on_result=on_result,
        )
        pub_t.join(timeout=1.0)
        return


if __name__ == "__main__":
    main()
