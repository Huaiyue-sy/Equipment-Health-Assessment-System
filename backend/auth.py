from __future__ import annotations

import os
import time
from functools import wraps

import jwt
import pymysql
from flask import request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash

SECRET_KEY = os.getenv("JWT_SECRET", "ihealthsim-secret-change-in-production")
JWT_EXPIRE_S = int(os.getenv("JWT_EXPIRE_S", "86400"))  # 24h

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB = os.getenv("MYSQL_DB", "ihealthsim")


def _get_db() -> pymysql.Connection:
    conn = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    return conn


def init_db() -> None:
    conn = _get_db()
    try:
        conn.cursor().execute("""
            CREATE TABLE IF NOT EXISTS users (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                username    VARCHAR(64)  NOT NULL UNIQUE,
                email       VARCHAR(128) NOT NULL UNIQUE,
                password    VARCHAR(256) NOT NULL,
                role        VARCHAR(32)  NOT NULL DEFAULT 'operator',
                created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_login  TIMESTAMP    NULL DEFAULT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
        # 默认账号 admin/admin123
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM users WHERE username = %s", ("admin",))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO users (username, email, password, role) VALUES (%s, %s, %s, %s)",
                ("admin", "admin@ihealthsim.local", generate_password_hash("admin123"), "admin"),
            )
            conn.commit()
    finally:
        conn.close()


def _create_token(user: dict) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "role": user["role"],
        "iat": now,
        "exp": now + JWT_EXPIRE_S,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def verify_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "未提供认证令牌"}), 401
        payload = verify_token(auth[7:])
        if payload is None:
            return jsonify({"error": "令牌无效或已过期"}), 401
        g.user = payload
        return f(*args, **kwargs)

    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        payload = verify_token(auth[7:]) if auth.startswith("Bearer ") else None
        if not payload or payload.get("role") != "admin":
            return jsonify({"error": "需要管理员权限"}), 403
        g.user = payload
        return f(*args, **kwargs)

    return decorated


def _perm_conn():
    return pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD,
        database=MYSQL_DB, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def get_user_devices(user_id: int) -> list[str]:
    """返回用户有权限查看的 asset_id 列表。* 表示全部设备。"""
    conn = _perm_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT asset_id FROM user_devices WHERE user_id = %s", (user_id,))
        rows = cur.fetchall()
        ids = [r["asset_id"] for r in rows]
        return ids
    finally:
        conn.close()


def check_device_permission(user_id: int, asset_id: str) -> bool:
    """检查用户是否有指定设备的查看权限。* 表示所有设备。"""
    devices = get_user_devices(user_id)
    return "*" in devices or asset_id in devices


def register_auth_routes(app):
    init_db()

    @app.post("/api/auth/register")
    def auth_register():
        data = request.get_json(silent=True) or {}
        username = (data.get("username") or "").strip()
        email = (data.get("email") or "").strip()
        password = data.get("password") or ""

        if not username or not email or not password:
            return jsonify({"error": "用户名、邮箱、密码不能为空"}), 400
        if len(username) < 2 or len(username) > 64:
            return jsonify({"error": "用户名长度 2-64 字符"}), 400
        if len(password) < 6:
            return jsonify({"error": "密码至少 6 位"}), 400

        conn = _get_db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM users WHERE username = %s", (username,))
            if cur.fetchone():
                return jsonify({"error": "用户名已存在"}), 409
            cur.execute("SELECT 1 FROM users WHERE email = %s", (email,))
            if cur.fetchone():
                return jsonify({"error": "邮箱已注册"}), 409

            cur.execute(
                "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                (username, email, generate_password_hash(password)),
            )
            conn.commit()
            return jsonify({"ok": True, "message": "注册成功"}), 201
        finally:
            conn.close()

    @app.post("/api/auth/login")
    def auth_login():
        data = request.get_json(silent=True) or {}
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""

        if not username or not password:
            return jsonify({"error": "用户名和密码不能为空"}), 400

        conn = _get_db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cur.fetchone()
            if not user or not check_password_hash(user["password"], password):
                return jsonify({"error": "用户名或密码错误"}), 401

            cur.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s", (user["id"],))
            conn.commit()

            token = _create_token(user)
            return jsonify({
                "ok": True,
                "token": token,
                "user": {"id": user["id"], "username": user["username"], "email": user["email"], "role": user["role"]},
            })
        finally:
            conn.close()

    @app.get("/api/auth/me")
    @login_required
    def auth_me():
        devices = get_user_devices(int(g.user["sub"]))
        user = dict(g.user)
        user["devices"] = devices
        return jsonify({"ok": True, "user": user})

    # ── 管理员：权限管理 ──

    @app.get("/api/admin/users")
    @admin_required
    def admin_users():
        conn = _perm_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, username, email, role, created_at, last_login FROM users ORDER BY id")
            users = cur.fetchall()
            for u in users:
                u["created_at"] = str(u["created_at"])
                u["last_login"] = str(u["last_login"]) if u["last_login"] else None
                u["devices"] = get_user_devices(u["id"])
            return jsonify({"ok": True, "users": users})
        finally:
            conn.close()

    @app.post("/api/admin/users/<int:user_id>/devices")
    @admin_required
    def admin_set_user_devices(user_id):
        data = request.get_json(silent=True) or {}
        devices = data.get("devices", [])  # ["*"] 表示全部

        if not isinstance(devices, list):
            return jsonify({"error": "devices 必须是数组"}), 400

        conn = _perm_conn()
        try:
            cur = conn.cursor()
            # 验证用户存在
            cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if not cur.fetchone():
                return jsonify({"error": "用户不存在"}), 404

            # 替换权限
            cur.execute("DELETE FROM user_devices WHERE user_id = %s", (user_id,))
            for asset_id in devices:
                cur.execute(
                    "INSERT INTO user_devices (user_id, asset_id, granted_by) VALUES (%s, %s, %s)",
                    (user_id, asset_id, int(g.user["sub"])),
                )
            conn.commit()
            return jsonify({"ok": True, "devices": get_user_devices(user_id)})
        finally:
            conn.close()
