# iHealthSim — 工业设备健康状态评估系统

基于 **仿真设备 + MQTT (EMQX) + 决策树 + Vue 前端** 的工业设备健康评估原型系统，实现从数据采集、特征工程、模型训练到实时在线评估的完整链路。

## 系统架构

```
┌──────────────┐     MQTT      ┌──────────┐     MQTT      ┌──────────────┐
│  仿真设备      │ ──────────→  │  EMQX    │ ──────────→  │  Flask 后端   │
│  (pub-device) │   publish    │ (Broker) │  subscribe   │  + 模型打分   │
└──────────────┘              └──────────┘              └──────┬───────┘
                                                               │
                                              ┌────────────────┼────────────────┐
                                              │                │                │
                                              ▼                ▼                ▼
                                         ┌─────────┐    ┌──────────┐    ┌──────────┐
                                         │ SSE 推送 │    │ REST API │    │ MySQL    │
                                         │ 实时看板  │    │ 查询/管理 │    │ 事件存储  │
                                         └────┬────┘    └──────────┘    └──────────┘
                                              │
                                              ▼
                                         ┌──────────┐
                                         │ Vue 前端  │
                                         │ 实时看板  │
                                         └──────────┘
```

## 功能特性

| 模块 | 说明 |
|------|------|
| **设备仿真** | 模拟旋转设备（泵/电机），生成 rpm/load/vib_rms/temp_c/motor_current_a 遥测数据，支持渐进退化与故障注入 |
| **MQTT 传输** | 仿真数据通过 MQTT 发布到 EMQX Broker，topic: `telemetry/raw/<asset_id>` |
| **特征工程** | 滑动窗口聚合（均值/标准差/分位数/趋势/Δ），支持离线批量和在线实时两种模式 |
| **决策树训练** | 基于 scikit-learn DecisionTreeClassifier，输出概率分布和可审计决策路径 |
| **在线打分** | 实时订阅 MQTT，窗口触发模型预测，含去抖/迟滞逻辑防止 prediction flutter |
| **Flask 后端** | MQTT 订阅 → 遥测存储 → 模型打分 → SSE 推送，提供 REST API |
| **Vue 前端** | 实时看板：设备切换、健康分数环、概率分布、诊断依据时间线、事件日志、诊断报告 |
| **用户认证** | JWT 认证，角色管理（admin/operator），设备级权限控制 |
| **多设备** | 同时监控 3 台设备（PUMP-001~003），前端自由切换 |

## 技术栈

| 层 | 技术 |
|----|------|
| 语言 | Python 3.11+ |
| 核心库 | numpy, pandas, scikit-learn, joblib |
| MQTT | paho-mqtt 2.x |
| 后端 | Flask + flask-cors |
| 前端 | Vue 3 + Vue Router + Vite |
| 数据库 | MySQL (认证 + 事件存储) |
| 消息队列 | EMQX (MQTT Broker) |

## 项目结构

```
.
├── src/ihealthsim/          # 核心 Python 包
│   ├── cli.py               # 命令行入口（12 个子命令）
│   ├── schemas.py           # 数据结构（TelemetryPoint / HealthResult）
│   ├── features.py          # 离线特征工程（窗口聚合）
│   ├── scoring.py           # OnlineScorer（在线打分 + 去抖 + 决策路径解释）
│   ├── train.py             # 决策树训练
│   ├── api.py               # FastAPI 接口（可选）
│   ├── mqtt_transport.py    # MQTT 客户端工具
│   ├── mqtt_collector.py    # MQTT → CSV 采集器
│   ├── mqtt_ingest.py       # 后台 MQTT → scorer 摄入
│   ├── mqtt_live.py         # MQTT 在线打分输出
│   └── sim/
│       ├── device.py        # 设备仿真器（物理模型 + 退化逻辑）
│       └── run_device_mqtt.py # 仿真设备 → MQTT 发布
├── backend/                 # Flask 后端
│   ├── app.py               # 主应用（路由 + 多设备仿真 + SSE）
│   ├── config.py            # 环境配置
│   ├── auth.py              # JWT 认证 + 设备权限
│   ├── state.py             # 内存状态管理
│   ├── scorer_worker.py     # 打分工作线程
│   ├── sse.py               # SSE 事件中心
│   └── mqtt_subscriber.py   # MQTT 订阅器
├── frontend/                # Vue 3 前端
│   ├── src/
│   │   ├── App.vue          # 主布局（导航栏 + 路由）
│   │   ├── api.js           # API 封装（REST + SSE）
│   │   ├── router/index.js  # 路由（登录/注册/看板/管理）
│   │   ├── style.css        # 全局设计系统
│   │   └── views/
│   │       ├── Login.vue    # 登录页
│   │       ├── Register.vue # 注册页
│   │       ├── Dashboard.vue # 实时看板（核心页面）
│   │       └── Admin.vue    # 用户权限管理
│   ├── index.html
│   └── vite.config.js       # Vite 配置（API 代理）
├── data/
│   ├── raw.csv              # 原始遥测数据
│   ├── features.csv         # 窗口特征
│   ├── schema.sql           # 数据库建表 SQL
│   └── auth.db              # SQLite 认证库（开发环境）
├── models/
│   └── tree.joblib          # 训练好的决策树模型
├── scripts/
│   └── generate_sim_data.py # 离线生成 CSV（不依赖 MQTT）
├── pyproject.toml           # 项目配置
├── requirements.txt         # Python 依赖
└── start.sh                 # 一键启动脚本
```

## 快速开始

### 前置条件

1. 启动 EMQX（或其他 MQTT Broker）在 `127.0.0.1:1883`
2. 启动 MySQL 在 `127.0.0.1:3306`，创建数据库 `ihealthsim`
3. Python 3.11+，Node.js 18+

```bash
# 克隆项目后，创建并激活虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
pip install -e .
```

### 一键启动（推荐）

```bash
bash start.sh
```

该脚本会依次启动 EMQX → Flask 后端 → Vue 前端，启动后访问：
- 前端: `http://localhost:5173`
- 后端: `http://localhost:5000`
- EMQX Dashboard: `http://localhost:18083`

默认管理员账号: `admin` / `admin123`

### 分步启动

#### 步骤 1：生成训练数据（通过 MQTT）

```bash
python -m ihealthsim.cli generate-data-mqtt \
  --mqtt-host 127.0.0.1 --mqtt-port 1883 \
  --seconds 7200 \
  --asset-id PUMP-001 \
  --fault-inject-at-s 1200 \
  --degradation-per-hour 0.06
```

输出: `data/raw.csv`

#### 步骤 2：特征提取 + 训练模型

```bash
python -m ihealthsim.cli make-features
python -m ihealthsim.cli train --feature-set online --max-depth 5 --min-samples-leaf 50
```

输出: `data/features.csv`, `models/tree.joblib`

#### 步骤 3：启动后端

```bash
MQTT_HOST=127.0.0.1 MQTT_PORT=1883 MODEL_PATH=models/tree.joblib \
python -m backend.app
```

后端启动后会自动：
- 连接 MQTT 并订阅 `telemetry/raw/#`
- 启动 3 台仿真设备（PUMP-001 ~ 003）
- 实时打分并通过 SSE 推送

#### 步骤 4：启动前端

```bash
cd frontend
npm install
npm run dev
```

访问 `http://localhost:5173`

## 核心概念

### 健康等级 (Health Level)

| 等级 | latent_health | 含义 | 颜色 |
|------|---------------|------|------|
| Lv0 (健康) | >= 0.80 | 设备正常运转 | 绿色 |
| Lv1 (注意) | 0.60 ~ 0.80 | 需要关注趋势 | 黄色 |
| Lv2 (警告) | 0.40 ~ 0.60 | 存在明显异常 | 红色 |
| Lv3 (危险) | < 0.40 | 立即停机检查 | 紫色 |

### 去抖/迟滞 (Debounce)

在线打分使用去抖逻辑避免预测抖动：
- 等级上升（恶化）：需连续 3 次确认才更新
- 等级下降（恢复）：需连续 5 次确认才更新
- 等级不变：重置计数器

### 决策路径解释

模型输出从根节点到叶子节点的完整决策路径，每条规则形如：
```
vib_rms_mean > 2.351 (val=3.142) → temp_c_mean <= 55.200 (val=52.100) → ...
```
前端将其渲染为诊断依据时间线，标注正常/异常。

## MQTT 消息格式

Topic: `telemetry/raw/<asset_id>`

```json
{
  "ts_ms": 1710000000000,
  "asset_id": "PUMP-001",
  "point": "temp_c",
  "value": 55.2,
  "quality": "good"
}
```

遥测点位: `rpm`, `load`, `vib_rms`, `temp_c`, `motor_current_a`, `label_health_level`

## API 参考

### 认证

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/auth/register` | 用户注册 | 无 |
| POST | `/api/auth/login` | 登录获取 token | 无 |
| GET | `/api/auth/me` | 获取当前用户信息 | Bearer Token |

### 数据

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/state?asset_id=PUMP-001` | 设备遥测快照 | Token |
| GET | `/api/flow` | MQTT/模型连接状态 | Token |
| GET | `/api/stream?token=xxx` | SSE 实时事件流 | URL Token |
| POST | `/api/simulate/start` | 启动恶化重演 | Token |
| GET | `/api/simulate/status` | 仿真运行状态 | Token |
| GET | `/api/events?asset_id=xxx&limit=50` | 查询事件日志 | Token |
| POST | `/api/events` | 创建事件记录 | Token |

### 管理

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/admin/users` | 用户列表 | Admin Token |
| POST | `/api/admin/users/:id/devices` | 设置用户设备权限 | Admin Token |

## CLI 命令参考

```bash
# 完整端到端流程
python -m ihealthsim.cli demo

# 发布模拟设备
python -m ihealthsim.cli pub-device --asset-id PUMP-001 --seconds 600

# 采集 MQTT 数据落盘
python -m ihealthsim.cli collect --duration-s 60

# 通过 MQTT 生成训练数据
python -m ihealthsim.cli generate-data-mqtt --seconds 7200

# 提取特征
python -m ihealthsim.cli make-features

# 训练决策树
python -m ihealthsim.cli train --max-depth 5 --feature-set online

# 在线订阅打分
python -m ihealthsim.cli live --duration-s 60

# 启动 API 服务（FastAPI 备用）
python -m ihealthsim.cli serve --host 0.0.0.0 --port 8000
```

## 离线模式（不依赖 MQTT）

```bash
# 直接生成 CSV 文件
python scripts/generate_sim_data.py --seconds 3600 --out data/raw.csv

## 文档

- [README.md](README.md) — 项目总览与快速开始
- [doc/ARCHITECTURE.md](doc/ARCHITECTURE.md) — 系统架构说明文档
- [doc/presentation.html](doc/presentation.html) — HTML 汇报 PPT（方向键翻页，F 全屏）

# 然后正常训练
python -m ihealthsim.cli make-features
python -m ihealthsim.cli train
```

## 常见问题

- **MQTT 连接失败**: 检查 EMQX 是否启动（`curl http://127.0.0.1:18083`），端口是否为 1883
- **模型加载失败**: 确保先执行训练步骤生成了 `models/tree.joblib`
- **MySQL 连接失败**: 检查 MySQL 是否启动，数据库 `ihealthsim` 是否已创建
- **SSE 断连**: 检查 token 是否过期，前端会自动重连
- **前端数据为空**: 确保后端已启动且 MQTT 有数据流入，检查 `/api/flow` 接口
