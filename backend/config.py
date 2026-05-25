from __future__ import annotations

import os


def _getenv(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    return v if v is not None and v != "" else default


class Settings:
    def __init__(self) -> None:
        self.mqtt_host: str = _getenv("MQTT_HOST", "127.0.0.1") or "127.0.0.1"
        self.mqtt_port: int = int(_getenv("MQTT_PORT", "1883") or "1883")
        self.mqtt_username: str | None = _getenv("MQTT_USERNAME", None)
        self.mqtt_password: str | None = _getenv("MQTT_PASSWORD", None)
        self.mqtt_base_topic: str = _getenv("MQTT_BASE_TOPIC", "telemetry/raw") or "telemetry/raw"
        self.mqtt_topic_filter: str = _getenv("MQTT_TOPIC_FILTER", f"{self.mqtt_base_topic}/#") or f"{self.mqtt_base_topic}/#"

        self.model_path: str = _getenv("MODEL_PATH", os.path.join("models", "tree.joblib")) or os.path.join("models", "tree.joblib")
        self.window_s: int = int(_getenv("WINDOW_S", "60") or "60")

        self.host: str = _getenv("HOST", "127.0.0.1") or "127.0.0.1"
        self.port: int = int(_getenv("PORT", "5000") or "5000")

        self.mysql_host: str = _getenv("MYSQL_HOST", "127.0.0.1") or "127.0.0.1"
        self.mysql_port: int = int(_getenv("MYSQL_PORT", "3306") or "3306")
        self.mysql_user: str = _getenv("MYSQL_USER", "root") or "root"
        self.mysql_password: str = _getenv("MYSQL_PASSWORD", "") or ""
        self.mysql_db: str = _getenv("MYSQL_DB", "ihealthsim") or "ihealthsim"


settings = Settings()
