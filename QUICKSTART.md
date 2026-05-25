# 快速启动

完整文档见 [README.md](README.md) 和 [doc/ARCHITECTURE.md](doc/ARCHITECTURE.md)。

## 一键启动

```bash
bash start.sh
```

启动后访问:
- 前端: `http://localhost:5173`
- 后端: `http://localhost:5000`
- 默认账号: `admin` / `admin123`

## 分步启动

```bash
# 1. 安装依赖
pip install -r requirements.txt
pip install -e .

# 2. 生成训练数据 + 训练模型
python -m ihealthsim.cli generate-data-mqtt --seconds 3600
python -m ihealthsim.cli make-features
python -m ihealthsim.cli train

# 3. 启动后端
MQTT_HOST=127.0.0.1 MQTT_PORT=1883 MODEL_PATH=models/tree.joblib \
python -m backend.app

# 4. 启动前端
cd frontend && npm install && npm run dev
```

## 纯离线模式（不需要 MQTT）

```bash
python scripts/generate_sim_data.py --seconds 3600 --out data/raw.csv
python -m ihealthsim.cli make-features
python -m ihealthsim.cli train
```
