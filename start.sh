#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "=== iHealthSim 快速启动 ==="

# 1. EMQX
if pgrep -f "emqx" > /dev/null 2>&1; then
  echo "[EMQX]  已在运行"
else
  echo "[EMQX]  启动中..."
  "$HOME/Downloads/emqx/bin/emqx" start 2>/dev/null || echo "[EMQX]  请手动启动"
fi

# 2. Backend
pkill -f "backend.app" 2>/dev/null || true
lsof -ti :5000 | xargs kill -9 2>/dev/null || true
sleep 1

echo "[Flask] 启动后端..."
export MQTT_HOST=127.0.0.1
export MQTT_PORT=1883
export MQTT_BASE_TOPIC=telemetry/raw
export MODEL_PATH=models/tree.joblib

.venv/bin/python -m backend.app &
BACKEND_PID=$!
echo "[Flask] PID=$BACKEND_PID"

# 3. Frontend
pkill -f "vite" 2>/dev/null || true
sleep 1

echo "[Vite]  启动前端..."
cd frontend
npx vite --port 5173 &
FRONTEND_PID=$!
echo "[Vite]  PID=$FRONTEND_PID"

cd "$ROOT"

echo ""
echo "=== 启动完成 ==="
echo "前端:   http://localhost:5173"
echo "后端:   http://localhost:5000"
echo "EMQX:   http://localhost:18083"
echo ""
echo "按 Ctrl+C 停止所有服务"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo '已停止'" EXIT
wait
