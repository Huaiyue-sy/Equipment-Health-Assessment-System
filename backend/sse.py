from __future__ import annotations

import json
import queue
import threading
from dataclasses import asdict
from typing import Any, Iterator


class SseHub:
    def __init__(self, *, max_queue: int = 1000) -> None:
        self._lock = threading.Lock()
        self._subs: set[queue.Queue[dict[str, Any]]] = set()
        self._max_queue = max_queue

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=self._max_queue)
        with self._lock:
            self._subs.add(q)
        return q

    def unsubscribe(self, q: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._subs.discard(q)

    def publish(self, event: str, data: Any) -> None:
        msg = {"event": event, "data": data}
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(msg)
            except queue.Full:
                try:
                    _ = q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    pass

    def stream_raw(self, q: queue.Queue[dict[str, Any]]) -> Iterator[tuple[str, str]]:
        """返回 (event, data_json_str) 元组，供调用方自行封装 SSE 格式。"""
        try:
            while True:
                msg = q.get()
                event = msg.get("event", "message")
                data = msg.get("data")
                yield event, json.dumps(data, ensure_ascii=False)
        finally:
            self.unsubscribe(q)

    def stream(self, q: queue.Queue[dict[str, Any]]) -> Iterator[str]:
        try:
            # initial hello
            yield "event: hello\n"
            yield f"data: {json.dumps({'ok': True})}\n\n"
            while True:
                msg = q.get()
                event = msg.get("event", "message")
                data = msg.get("data")
                yield f"event: {event}\n"
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        finally:
            self.unsubscribe(q)
