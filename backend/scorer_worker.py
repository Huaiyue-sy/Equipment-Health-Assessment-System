from __future__ import annotations

import threading
import time
from dataclasses import asdict

from ihealthsim.scoring import OnlineScorer
from ihealthsim.schemas import TelemetryPoint

from .sse import SseHub
from .state import InMemoryState


class ScorerWorker:
    def __init__(self, *, scorer: OnlineScorer, state: InMemoryState, hub: SseHub) -> None:
        self.scorer = scorer
        self.state = state
        self.hub = hub

        self._lock = threading.Lock()

    def on_point(self, p: TelemetryPoint) -> None:
        # OnlineScorer 内部是纯 Python/NumPy/Pandas，不保证线程安全；用锁保护
        with self._lock:
            hr = self.scorer.ingest(p)
        if hr is not None:
            self.state.set_health(hr)
            self.hub.publish("prediction", asdict(hr))

            # 推送报警事件
            alarms = self.scorer.latest_alarms(p.asset_id)
            for alarm in alarms:
                self.hub.publish("alarm", asdict(alarm))


class PollingScorerWorker:
    """备用：如果你不想在 MQTT 回调线程里跑模型，可启用轮询方式。当前 demo 默认不用。"""

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError
