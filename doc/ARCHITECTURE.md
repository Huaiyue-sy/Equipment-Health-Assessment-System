# iHealthSim 系统架构说明文档

## 1. 项目概述

### 1.1 项目定位

iHealthSim 是一套**工业设备健康状态评估原型系统**，用于演示从设备数据采集到健康评估的完整技术链路。系统采用全仿真方式生成工业旋转设备（泵、电机等）的遥测数据，通过 MQTT 协议传输到后端进行实时分析，使用决策树模型输出设备健康评分和诊断依据，最终在 Web 前端以可视化看板形式呈现。

### 1.2 核心价值

- **零硬件依赖**：所有设备数据均由仿真器生成，无需连接真实 PLC/传感器
- **完整链路**：覆盖 仿真→传输→采集→特征→训练→打分→展示 全流程
- **可审计**：决策树模型输出完整决策路径，非黑盒预测
- **可扩展**：MQTT 消息格式标准，可无缝替换为真实设备数据源

### 1.3 适用场景

- 工业物联网 (IIoT) 原型验证
- 预测性维护 (PdM) 方案演示
- 设备健康管理系统 (EHM) 技术选型参考
- 教学培训（工业大数据、机器学习应用）

---

## 2. 系统架构

### 2.1 架构图

```
                           ┌──────────────────────────────┐
                           │        Vue 3 前端 (5173)       │
                           │  ┌──────┐ ┌──────┐ ┌───────┐ │
                           │  │Login │ │Dash- │ │Admin  │ │
                           │  │      │ │board │ │       │ │
                           │  └──────┘ └──┬───┘ └───────┘ │
                           │              │ SSE / REST      │
                           └──────────────┼────────────────┘
                                          │
                           ┌──────────────┼────────────────┐
                           │  Flask 后端 (5000)            │
                           │              │                 │
                           │  ┌───────────┴─────────────┐  │
                           │  │      REST API            │  │
                           │  │  /api/state, /api/flow,  │  │
                           │  │  /api/auth/*, /api/events │  │
                           │  └───────────┬─────────────┘  │
                           │              │                 │
                           │  ┌───────────┴─────────────┐  │
                           │  │      SSE 事件流           │  │
                           │  │  telemetry / prediction  │  │
                           │  │  / flow                   │  │
                           │  └───────────┬─────────────┘  │
                           │              │                 │
                           │  ┌───────────┴─────────────┐  │
                           │  │   MQTT Subscriber        │  │
                           │  │   (paho-mqtt loop)       │  │
                           │  └───────────┬─────────────┘  │
                           │              │                 │
                           │  ┌───────────┴─────────────┐  │
                           │  │  InMemoryState           │  │
                           │  │  (遥测缓冲 + 健康结果)    │  │
                           │  └───────────┬─────────────┘  │
                           │              │                 │
                           │  ┌───────────┴─────────────┐  │
                           │  │  ScorerWorker            │  │
                           │  │  (OnlineScorer 打分)     │  │
                           │  └─────────────────────────┘  │
                           │                                │
                           │  ┌─────────────────────────┐  │
                           │  │  Auth (JWT + MySQL)      │  │
                           │  └─────────────────────────┘  │
                           └──────────────┬────────────────┘
                                          │ subscribe
                           ┌──────────────┴────────────────┐
                           │         EMQX Broker            │
                           │      127.0.0.1:1883           │
                           │   topic: telemetry/raw/#      │
                           └──────────────┬────────────────┘
                                          │ publish
                           ┌──────────────┴────────────────┐
                           │      仿真设备发布端             │
                           │  (DeviceSimulator x N)        │
                           │  PUMP-001 / PUMP-002 / ...    │
                           └──────────────────────────────┘
```

### 2.2 数据流

```
仿真设备 step()                         Flask 后端
  │                                       │
  │ 1. 更新 latent_health                 │
  │ 2. 计算 rpm/load/                     │
  │    vib/temp/current                   │
  │ 3. 封装 TelemetryPoint                │
  │                                       │
  ├─ publish ──→ EMQX ── subscribe ──→    │
  │                                       │
  │                                    MqttSubscriber
  │                                       │
  │                                    InMemoryState.ingest()
  │                                       │
  │                                    SSEHub.publish("telemetry")
  │                                       │
  │                                    ScorerWorker.on_point()
  │                                       │
  │                                    OnlineScorer.ingest()
  │                                       │
  │                                    窗口数据够了？
  │                                       │
  │                                    YES → 构建特征向量
  │                                    │
  │                                    Pipeline.predict()
  │                                    │
  │                                    去抖/迟滞
  │                                    │
  │                                    HealthResult
  │                                       │
  │                                    SSEHub.publish("prediction")
  │                                       │
  │                                        ├─ SSE → 前端 Dashboard
  │                                        └─ MySQL → events 表
```

---

## 3. 模块详解

### 3.1 `src/ihealthsim/sim/device.py` — 设备仿真器

**DeviceSimulator** 是系统的数据源，模拟旋转机械（泵/电机等）的物理行为。

#### 仿真模型

设备内部维护一个 `latent_health`（潜在健康度）变量，范围 [0.0, 1.0]：

- **健康退化**：每秒按 `degradation_per_hour / 3600` 的速度衰减，叠加高斯噪声模拟不均匀退化
- **故障注入**：在 `fault_inject_at_s` 时刻后，退化速度提升 3 倍
- **随机恢复**：每秒有 5% 概率发生微小恢复（模拟设备冷却等）
- **工况切换**：每约 10 分钟切换一次运行工况（6 种工况循环），每种工况对应不同的转速和负载组合
- **环境温度漂移**：正弦波模拟环境温度变化，周期 10-30 分钟
- **传感器噪声**：退化越严重，测量噪声越大（×3 量级）
- **瞬态尖峰**：每秒 0.05% 概率的异常瞬态值

#### 输出点位

| 点位 | 说明 | 范围 |
|------|------|------|
| rpm | 转速 | 1500-2900 |
| load | 负载比 | 0.1-1.0 |
| vib_rms | 振动 RMS | 随健康恶化上升 |
| temp_c | 温度 (°C) | 随健康恶化上升 |
| motor_current_a | 电机电流 (A) | 随健康恶化上升 |
| label_health_level | 健康标签 | 0-3（监督训练用） |

#### Key Config

```python
DeviceSimConfig(
    asset_id="PUMP-001",
    ambient_temp_c=25.0,       # 环境温度
    degradation_per_hour=0.03,  # 退化速度
    fault_inject_at_s=3600,     # 故障注入时间
    degradation_std=0.5,        # 退化噪声
    transient_prob_per_s=0.0005,# 瞬态概率
)
```

### 3.2 `src/ihealthsim/features.py` — 特征工程

将原始 long-format 遥测数据转换为窗口特征矩阵。

#### 处理流程

1. **Pivot**：long → wide 格式（每个点位一列）
2. **窗口划分**：按 `window_s`（默认 60s）分组
3. **基础统计**：对每个点位计算 mean/std/min/max/p95
4. **趋势特征**：对 temp_c/vib_rms/motor_current_a 计算窗口内线性斜率
5. **Δ 特征**：与上一窗口均值的差值
6. **归一化特征**：`vib_rms_mean / (rpm_mean / 1000)` 的工况归一化振动

#### 输出格式

`data/features.csv` — 每行一个窗口，包含约 30 个特征列 + 标签列 `y`

### 3.3 `src/ihealthsim/train.py` — 模型训练

使用 scikit-learn 的 Pipeline：

```
ColumnTransformer(SimpleImputer(median)) → DecisionTreeClassifier
```

#### 训练特性

- **时间序列分割**：按窗口时间顺序切分训练/测试集（非随机，避免未来信息泄露）
- **在线特征子集**：`feature_set=online` 时只使用 OnlineScorer 可实时计算的特征，避免训练-在线不一致
- **类别平衡**：`class_weight='balanced'` 处理健康等级不平衡分布
- **模型打包**：将 pipeline + feature_cols + report 整体序列化为 joblib 文件

#### 训练参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| max_depth | 5 | 决策树最大深度 |
| min_samples_leaf | 50 | 叶节点最小样本数 |
| feature_set | online | 特征集选择（online/all） |
| test_size | 0.3 | 测试集比例 |

### 3.4 `src/ihealthsim/scoring.py` — 在线打分

**OnlineScorer** 是实时推理核心。

#### 工作流程

1. **缓冲**：每个 asset_id 维护一个 TelemetryPoint 队列
2. **触发**：以 `temp_c` 点位到达作为窗口边界触发器（每个窗口只打分一次）
3. **窗口提取**：取出 `[window_start, window_end)` 内的所有点位
4. **在线特征**：计算 8 个实时可算的特征（与 `ONLINE_FEATURE_COLS` 一致）：
   - `rpm_mean`, `load_mean`, `vib_rms_mean`, `temp_c_mean`, `motor_current_a_mean`
   - `vib_rms_std`, `temp_c_std`, `vib_rms_norm`
5. **预测**：通过 pipeline 得到 level + proba
6. **去抖**：基于等级的迟滞逻辑
7. **解释**：遍历决策树路径，输出可读的决策链

#### 去抖配置

```python
DebounceConfig(
    abnormal_level=2,   # 等级 >=2 被视为异常
    raise_n=3,          # 连续 3 次确认上升
    recover_n=5,        # 连续 5 次确认恢复（恢复更保守）
)
```

### 3.5 `src/ihealthsim/cli.py` — CLI 入口

提供 12 个子命令，覆盖完整工作流：

| 子命令 | 功能 |
|--------|------|
| `demo` | 端到端完整流程（生成→特征→训练→在线） |
| `pub-device` | 发布模拟设备遥测到 MQTT |
| `collect` | 从 MQTT 订阅并采集落盘 CSV |
| `generate-data-mqtt` | 同进程内采集+发布生成 raw.csv |
| `make-features` | 从 raw.csv 生成窗口特征 |
| `train` | 训练决策树 |
| `live` | 订阅 MQTT 在线打分输出 |
| `serve` | 启动 FastAPI 服务 |

### 3.6 后端模块

#### `backend/app.py` — Flask 主应用

- 创建 Flask app，注册所有路由
- 初始化 MQTT 订阅器、状态管理器、SSE 中心、打分工作器
- 启动时自动拉起 3 台仿真设备进程
- 提供 "/api/*" REST 接口 + SSE 流

#### `backend/auth.py` — 认证授权

- JWT (HS256) 认证
- 用户注册/登录（密码 bcrypt 哈希）
- 角色管理：admin（管理员）/ operator（操作员）
- 设备级权限：admin 可为每个用户设置可访问的设备列表
- 默认管理员账号：admin / admin123

#### `backend/state.py` — 内存状态

- `InMemoryState`：线程安全的内存数据存储
- 维护遥测字典、环形缓冲队列、健康结果映射
- 提供 snapshot() 方法用于 API 查询

#### `backend/sse.py` — 事件中心

- `SseHub`：发布-订阅模式的事件中心
- 支持多客户端同时订阅
- 自动丢弃慢消费者的过期消息
- 事件类型：`telemetry` / `prediction` / `flow`

#### `backend/mqtt_subscriber.py` — MQTT 订阅

- 基于 paho-mqtt 的异步订阅器
- 解析 JSON 消息为 TelemetryPoint
- 推送到 State + SSE Hub + ScorerWorker

#### `backend/scorer_worker.py` — 打分线程

- 在锁保护下调用 OnlineScorer.ingest()
- 将 HealthResult 写入 State 和 SSE Hub

### 3.7 前端模块

#### 路由设计

| 路径 | 组件 | 认证 | 说明 |
|------|------|------|------|
| `/login` | Login.vue | Guest | 登录页 |
| `/register` | Register.vue | Guest | 注册页 |
| `/dashboard` | Dashboard.vue | Token | 实时看板（主页） |
| `/admin` | Admin.vue | Admin Token | 用户权限管理 |

#### Dashboard.vue — 核心页面

- **状态指示条**：MQTT 连接状态、模型加载状态、数据流入延迟
- **设备标签栏**：多设备切换，标签上显示当前健康等级
- **预测概览**：
  - 左侧：健康分数环形图 + 等级徽章
  - 右侧：四级概率分布柱状图
- **诊断依据时间线**：解析决策路径，渲染为步骤式流程图，标注正常/异常
- **实时遥测表**：最新各点位数值
- **事件日志**：健康等级变化、异常告警
- **诊断报告**：设备概览、异常指标、决策路径、维护建议

**恶化重演**功能：点击按钮重新启动 3 台设备的完整退化过程。

---

## 4. 数据库设计

### MySQL 表结构

#### users 表

```sql
CREATE TABLE users (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    username    VARCHAR(64)  NOT NULL UNIQUE,
    email       VARCHAR(128) NOT NULL UNIQUE,
    password    VARCHAR(256) NOT NULL,  -- werkzeug hash
    role        VARCHAR(32)  NOT NULL DEFAULT 'operator',
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login  TIMESTAMP    NULL
);
```

#### events 表

```sql
CREATE TABLE events (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    asset_id     VARCHAR(64)  NOT NULL,
    type         VARCHAR(32)  NOT NULL,
    message      TEXT         NOT NULL,
    health_level INT          NULL,
    health_score FLOAT        NULL,
    created_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

#### user_devices 表

```sql
CREATE TABLE user_devices (
    id        INT AUTO_INCREMENT PRIMARY KEY,
    user_id   INT          NOT NULL,
    asset_id  VARCHAR(64)  NOT NULL,  -- '*' = all devices
    granted_by INT         NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

---

## 5. 部署指南

### 5.1 开发环境

```bash
# 1. 启动 EMQX
~/Downloads/emqx/bin/emqx start

# 2. 启动 MySQL（或 Docker）
docker run -d --name mysql -p 3306:3306 \
  -e MYSQL_ROOT_PASSWORD=root \
  -e MYSQL_DATABASE=ihealthsim \
  mysql:8

# 3. 初始化 Python 环境
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

# 4. 训练模型
python -m ihealthsim.cli generate-data-mqtt --seconds 3600
python -m ihealthsim.cli make-features
python -m ihealthsim.cli train

# 5. 启动后端
MQTT_HOST=127.0.0.1 MQTT_PORT=1883 MODEL_PATH=models/tree.joblib \
python -m backend.app

# 6. 启动前端 (新终端)
cd frontend
npm install
npm run dev
```

### 5.2 一键启动

```bash
bash start.sh
```

### 5.3 Docker 部署（建议）

```yaml
# docker-compose.yml
version: '3.8'
services:
  emqx:
    image: emqx/emqx:latest
    ports:
      - "1883:1883"
      - "18083:18083"

  mysql:
    image: mysql:8
    environment:
      MYSQL_ROOT_PASSWORD: root
      MYSQL_DATABASE: ihealthsim
    ports:
      - "3306:3306"

  backend:
    build: .
    ports:
      - "5000:5000"
    environment:
      MQTT_HOST: emqx
      MQTT_PORT: 1883
      MYSQL_HOST: mysql
      MODEL_PATH: models/tree.joblib
    depends_on:
      - emqx
      - mysql

  frontend:
    build: ./frontend
    ports:
      - "5173:5173"
    depends_on:
      - backend
```

### 5.4 环境变量说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| MQTT_HOST | 127.0.0.1 | MQTT Broker 地址 |
| MQTT_PORT | 1883 | MQTT Broker 端口 |
| MQTT_USERNAME | (空) | MQTT 用户名 |
| MQTT_PASSWORD | (空) | MQTT 密码 |
| MQTT_BASE_TOPIC | telemetry/raw | MQTT 主题前缀 |
| MQTT_TOPIC_FILTER | telemetry/raw/# | 订阅通配符 |
| MODEL_PATH | models/tree.joblib | 模型文件路径 |
| WINDOW_S | 60 | 打分窗口大小(秒) |
| HOST | 127.0.0.1 | Flask 监听地址 |
| PORT | 5000 | Flask 监听端口 |
| MYSQL_HOST | 127.0.0.1 | MySQL 地址 |
| MYSQL_PORT | 3306 | MySQL 端口 |
| MYSQL_USER | root | MySQL 用户 |
| MYSQL_PASSWORD | (空) | MySQL 密码 |
| MYSQL_DB | ihealthsim | MySQL 数据库名 |
| JWT_SECRET | ihealthsim-secret-change-in-production | JWT 密钥 |
| JWT_EXPIRE_S | 86400 | Token 有效期(秒) |

---

## 6. 扩展指南

### 6.1 接入真实设备数据

修改设备数据源只需确保 MQTT 消息格式一致：

```json
{
  "ts_ms": 1710000000000,
  "asset_id": "REAL-PUMP-001",
  "point": "temp_c",
  "value": 55.2,
  "quality": "good"
}
```

发布到 `telemetry/raw/REAL-PUMP-001` 即可被系统自动接收和处理。

### 6.2 替换模型

当前使用决策树，可以替换为任意 scikit-learn 兼容模型：

1. 修改 `src/ihealthsim/train.py` 中的分类器
2. 确保 `OnlineScorer` 中的特征计算与训练时的特征列对齐
3. 更新 `ONLINE_FEATURE_COLS` 常量

### 6.3 增加设备类型

1. 创建新的 DeviceSimulator 子类（当前为通用旋转设备模型）
2. 在 `backend/app.py` 的 `MULTI_DEVICES` 中添加新设备配置
3. 在 `frontend/src/views/Admin.vue` 的 `deviceList` 中添加设备 ID

### 6.4 增加遥测点位

1. 在 `DeviceSimulator.step()` 中添加新点位
2. 在 `features.py` 中添加对应的聚合逻辑
3. 在 `ONLINE_FEATURE_COLS` 中添加对应的在线特征
4. 在前端 `POINT_LABELS` 和 `FEATURE_NAMES` 中添加中文映射

---

## 7. 关键设计决策

### 7.1 为什么用决策树而不是深度学习？

- **可解释性**：决策树输出完整决策路径，可用于审计和调试
- **数据量**：仿真数据通常只有几千到几万个窗口，决策树足够
- **部署简单**：单个 joblib 文件，无需 GPU，推理速度毫秒级
- **原型性质**：本系统面向演示和验证，决策树是合理的 baseline

### 7.2 为什么用 MQTT 而不是 HTTP/WebSocket？

MQTT 是工业物联网的事实标准协议：
- **发布/订阅**：设备只需发布，不关心谁在消费
- **QoS**：支持至少一次 / 最多一次 / 仅一次 的消息保证
- **低带宽**：二进制协议，适合弱网环境
- **生态**：与 EMQX、HiveMQ、AWS IoT 等兼容

### 7.3 为什么 SSE 而不是 WebSocket？

- **单向推送**：前端只需接收服务端推送，不需要发送
- **更简单**：SSE 基于 HTTP，无需特殊协议升级
- **自动重连**：浏览器原生支持断线重连
- **兼容性好**：所有现代浏览器支持

### 7.4 去抖/迟滞的必要性

实时预测中，传感器噪声和瞬态工况变化可能导致模型输出在等级边界反复横跳。去抖逻辑：
- 等级上升时需要较少确认（快速报警）
- 等级恢复时需要更多确认（避免误解除）
- 模拟了工业中 "报警容易解除难" 的实际需求

---

## 8. 依赖清单

### Python

```
numpy>=2.0           # 数值计算
pandas>=2.2          # 数据处理
scikit-learn>=1.5    # 机器学习
joblib>=1.4          # 模型序列化
paho-mqtt>=2.1       # MQTT 客户端
flask>=3.0           # Web 框架
flask-cors>=4.0      # 跨域支持
pyjwt>=2.8           # JWT 认证
pymysql>=1.1         # MySQL 驱动
fastapi>=0.111       # API 框架（备用）
uvicorn>=0.30        # ASGI 服务器（备用）
pydantic>=2.7        # 数据校验（备用）
rich>=13.7           # CLI 美化输出
```

### Node.js (前端)

```
vue@3                # UI 框架
vue-router@4         # 路由
vite@5               # 构建工具
@vitejs/plugin-vue   # Vite Vue 插件
```

---

## 9. 版本记录

| 版本 | 日期 | 变更 |
|------|------|------|
| 0.1.0 | 2025-05 | 初始版本：仿真器 + 决策树 + MQTT + Flask + Vue |

---

## 10. 项目路线图

- [ ] 支持更多设备类型（压缩机、风机等）
- 替换为 XGBoost/LightGBM 模型可选
- 增加历史趋势图表（ECharts）
- 报警规则引擎（阈值+趋势+组合规则）
- [ ] Docker 一键部署
- [ ] WebSocket 双向通信
- [ ] 多语言支持（i18n）
