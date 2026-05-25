from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import threading
from dataclasses import asdict

import pymysql
from flask import Flask, Response, g, jsonify, request
from flask_cors import CORS

from ihealthsim.mqtt_transport import MqttConfig
from ihealthsim.schemas import AlarmEvent
from ihealthsim.scoring import OnlineScorer

from .auth import register_auth_routes, login_required, admin_required, verify_token, check_device_permission, get_user_devices
from .config import settings
from .mqtt_subscriber import MqttSubscriber
from .scorer_worker import ScorerWorker
from .sse import SseHub
from .state import InMemoryState


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

    # 注册认证路由 /api/auth/register, /api/auth/login, /api/auth/me
    register_auth_routes(app)

    state = InMemoryState(max_points=2000)
    hub = SseHub(max_queue=2000)

    # load model
    scorer = OnlineScorer(settings.model_path, window_s=settings.window_s)
    state.mark_model_loaded()
    hub.publish("flow", {"stage": "model", "status": "loaded", "model_path": settings.model_path})

    scorer_worker = ScorerWorker(scorer=scorer, state=state, hub=hub)

    mqtt_cfg = MqttConfig(
        host=settings.mqtt_host,
        port=settings.mqtt_port,
        username=settings.mqtt_username,
        password=settings.mqtt_password,
        base_topic=settings.mqtt_base_topic,
    )

    subscriber = MqttSubscriber(
        cfg=mqtt_cfg,
        topic_filter=settings.mqtt_topic_filter,
        state=state,
        hub=hub,
        on_point=scorer_worker.on_point,
    )

    subscriber.start()

    @app.get("/api/health")
    def api_health():
        return jsonify({"ok": True, "time": time.time()})

    @app.get("/api/state")
    @login_required
    def api_state():
        asset = request.args.get("asset_id", "PUMP-001")
        user_id = int(g.user["sub"])
        if not check_device_permission(user_id, asset):
            return jsonify({"error": "无权访问该设备"}), 403
        return jsonify(state.snapshot(asset_id=asset))

    @app.get("/api/trends")
    @login_required
    def api_trends():
        asset = request.args.get("asset_id", "PUMP-001")
        user_id = int(g.user["sub"])
        if not check_device_permission(user_id, asset):
            return jsonify({"error": "无权访问该设备"}), 403
        return jsonify({
            "health_history": state.health_trend(asset),
            "alarm_history": state.alarm_trend(asset),
        })

    @app.get("/api/flow")
    @login_required
    def api_flow():
        snap = state.snapshot()
        now = time.time()
        last = snap.get("last_message_at")
        age_s = None if last is None else float(now - float(last))
        return jsonify(
            {
                "mqtt_connected": snap.get("mqtt_connected", False),
                "model_loaded": snap.get("model_loaded", False),
                "last_message_age_s": age_s,
                "topic_filter": settings.mqtt_topic_filter,
                "mqtt_host": settings.mqtt_host,
                "mqtt_port": settings.mqtt_port,
            }
        )

    # ── 事件日志 ──
    def _events_db():
        return pymysql.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_db,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )

    @app.post("/api/events")
    @login_required
    def api_events_create():
        data = request.get_json(silent=True) or {}
        asset_id = data.get("asset_id", "PUMP-001")
        event_type = data.get("type", "")
        message = data.get("message", "")
        health_level = data.get("health_level")
        health_score = data.get("health_score")

        if not event_type or not message:
            return jsonify({"error": "type 和 message 不能为空"}), 400

        conn = _events_db()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO events (asset_id, type, message, health_level, health_score) VALUES (%s, %s, %s, %s, %s)",
                (asset_id, event_type, message, health_level, health_score),
            )
            conn.commit()
            return jsonify({"ok": True, "id": cur.lastrowid}), 201
        finally:
            conn.close()

    @app.get("/api/events")
    @login_required
    def api_events_list():
        asset_id = request.args.get("asset_id", "PUMP-001")
        user_id = int(g.user["sub"])
        if not check_device_permission(user_id, asset_id):
            return jsonify({"error": "无权访问该设备"}), 403
        limit = int(request.args.get("limit", "50"))
        conn = _events_db()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, asset_id, type, message, health_level, health_score, created_at FROM events WHERE asset_id = %s ORDER BY id DESC LIMIT %s",
                (asset_id, limit),
            )
            rows = cur.fetchall()
            for r in rows:
                r["created_at"] = str(r["created_at"])
            return jsonify({"ok": True, "events": rows})
        finally:
            conn.close()

    @app.get("/api/stream")
    def api_stream():
        token = request.args.get("token", "")
        payload = verify_token(token)
        if not payload:
            return jsonify({"error": "未认证"}), 401
        user_id = int(payload["sub"])
        allowed = get_user_devices(user_id)
        has_all = "*" in allowed

        def filtered_stream():
            for event, data_str in hub.stream_raw(hub.subscribe()):
                if not has_all and event in ("telemetry", "prediction", "alarm"):
                    try:
                        d = json.loads(data_str)
                    except Exception:
                        continue
                    aid = d.get("asset_id", "")
                    if aid and aid not in allowed:
                        continue
                if event == "alarm":
                    try:
                        alarm_data = json.loads(data_str)
                        state.add_alarm(AlarmEvent(**alarm_data))
                    except Exception:
                        pass
                yield f"event: {event}\n"
                yield f"data: {data_str}\n\n"

        return Response(filtered_stream(), mimetype="text/event-stream")

    # ── 仿真重演（多设备）──
    _sim_procs: list[subprocess.Popen] = []

    MULTI_DEVICES = [
        # (asset_id, fault_inject_at_s, degradation_per_hour, seconds, sleep_s)
        ("PUMP-001", 10,  6.0, 600, 1.0),   # 快速
        ("PUMP-002", 20,  4.5, 600, 1.0),   # 中速
        ("PUMP-003", 15,  5.0, 600, 1.0),   # 适中
    ]

    def _start_all_sims():
        nonlocal _sim_procs
        # 杀掉旧进程
        for p in _sim_procs:
            try:
                p.kill()
                p.wait(timeout=3)
            except Exception:
                pass
        _sim_procs = []

        python = sys.executable
        for asset_id, fault_s, deg_hr, secs, sleep_s in MULTI_DEVICES:
            p = subprocess.Popen(
                [
                    python, "-m", "ihealthsim.cli", "pub-device",
                    "--mqtt-host", settings.mqtt_host,
                    "--mqtt-port", str(settings.mqtt_port),
                    "--asset-id", asset_id,
                    "--seconds", str(secs),
                    "--sleep-s", str(sleep_s),
                    "--fault-inject-at-s", str(fault_s),
                    "--degradation-per-hour", str(deg_hr),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _sim_procs.append(p)
        return True

    # 启动时自动开始模拟
    threading.Thread(target=_start_all_sims, daemon=True).start()

    @app.post("/api/simulate/start")
    @login_required
    def api_simulate_start():
        threading.Thread(target=_start_all_sims, daemon=True).start()
        return jsonify({"ok": True, "message": "仿真已启动，3 台设备渐进退化"})

    @app.get("/api/simulate/status")
    @login_required
    def api_simulate_status():
        nonlocal _sim_procs
        running = any(p.poll() is None for p in _sim_procs)
        return jsonify({"running": running})

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host=settings.host, port=settings.port, debug=False, threaded=True)
