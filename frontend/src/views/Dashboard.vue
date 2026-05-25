<template>
  <div class="dashboard" v-cloak>

    <!-- 状态指示条 -->
    <div class="status-bar">
      <div class="status-item">
        <span class="status-dot" :class="flow.mqtt_connected ? 'dot-green' : 'dot-red'"></span>
        <span>MQTT {{ flow.mqtt_connected ? '已连接' : '未连接' }}</span>
      </div>
      <div class="status-item">
        <span class="status-dot" :class="flow.model_loaded ? 'dot-green' : 'dot-red'"></span>
        <span>模型 {{ flow.model_loaded ? '已加载' : '未加载' }}</span>
      </div>
      <div class="status-item muted">
        {{ dataAgeText }}
      </div>
      <div class="status-spacer"></div>
      <button class="btn-replay" :disabled="replaying" @click="startReplay">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
        {{ replaying ? '重演中…' : '恶化重演' }}
      </button>
    </div>

    <!-- 设备标签栏 -->
    <div class="device-tabs">
      <button
        v-for="d in deviceList"
        :key="d"
        class="device-tab"
        :class="{ 'tab-active': assetId === d }"
        @click="switchDevice(d)"
      >
        <span class="tab-name">{{ d }}</span>
        <span class="tab-level" :class="'tab-lv-' + (devicePredictions[d]?.health_level ?? -1)">
          {{ deviceLevelText(d) }}
        </span>
      </button>
    </div>

    <!-- 预测结果 — 独立全宽模块 -->
    <div class="prediction-hero">
      <div class="hero-inner">

        <!-- 左侧：等级 + 分数环 -->
        <div class="hero-visual">
          <div class="score-ring-wrap">
            <svg class="score-ring" viewBox="0 0 120 120">
              <circle class="ring-bg" cx="60" cy="60" r="52" />
              <circle class="ring-fill" cx="60" cy="60" r="52"
                :stroke-dasharray="scoreDasharray"
                :stroke="scoreColor" />
            </svg>
            <div class="ring-center">
              <span class="ring-value">{{ scoreText }}</span>
              <span class="ring-unit">分</span>
            </div>
          </div>

          <div class="level-info">
            <div class="level-badge" :class="levelClass">{{ levelText }}</div>
            <div class="level-label">健康等级</div>
          </div>
        </div>

        <!-- 右侧：概率分布 -->
        <div class="hero-detail">
          <h3 class="detail-title">预测概率分布</h3>
          <div class="proba-chart">
            <div v-for="(item, i) in probaItems" :key="i" class="proba-row">
              <span class="proba-label" :class="`proba-label-${i}`">{{ item.label }}</span>
              <div class="proba-track">
                <div class="proba-fill" :class="`proba-fill-${i}`"
                  :style="{ width: item.pct + '%' }"></div>
              </div>
              <span class="proba-val">{{ item.pct.toFixed(1) }}%</span>
            </div>
          </div>
        </div>

      </div>

      <!-- 底部：诊断依据 -->
      <div class="hero-foot" v-if="explainNodes.length">
        <span class="foot-label">诊断依据</span>
        <div class="diagnosis-timeline">
          <div v-for="(node, i) in explainNodes" :key="i" class="diag-node"
            :class="{ 'diag-abnormal': node.abnormal }">
            <div class="diag-left">
              <div class="diag-step" :class="{ 'diag-step-warn': node.abnormal }">{{ i + 1 }}</div>
              <div v-if="i < explainNodes.length - 1" class="diag-line"></div>
            </div>
            <div class="diag-right">
              <div class="diag-head">
                <span class="diag-feat">{{ node.feature }}</span>
                <span v-if="node.abnormal" class="diag-badge">异常</span>
                <span v-else class="diag-badge diag-badge-ok">正常</span>
              </div>
              <div class="diag-desc">{{ node.description }}</div>
            </div>
          </div>
        </div>
        <p class="explain-summary">{{ explainSummary }}</p>
      </div>
    </div>

    <!-- 趋势图表区 -->
    <div class="trends-section" v-if="prediction">
      <div class="trend-card">
        <h3 class="card-head">健康分数趋势</h3>
        <div ref="scoreChartRef" class="chart-box"></div>
      </div>
      <div class="trend-card">
        <h3 class="card-head">遥测趋势</h3>
        <div ref="telemetryChartRef" class="chart-box"></div>
      </div>
    </div>

    <!-- 报警区 -->
    <div class="alarms-section" v-if="activeAlarms.length">
      <div class="alarm-header" @click="alarmsCollapsed = !alarmsCollapsed">
        <h3 class="card-head alarm-head-title">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
          当前报警 ({{ activeAlarms.length }})
        </h3>
        <span class="alarm-collapse-icon" :class="{ collapsed: alarmsCollapsed }">▾</span>
      </div>
      <div class="alarm-list" :class="{ collapsed: alarmsCollapsed }">
        <div v-for="(a, i) in activeAlarms" :key="i" class="alarm-item" :class="'alarm-' + a.severity">
          <span class="alarm-type-badge">{{ alarmTypeText(a.rule_type) }}</span>
          <span class="alarm-msg">{{ a.message }}</span>
          <span class="alarm-time">{{ formatAlarmTime(a.ts_ms) }}</span>
        </div>
      </div>
      <div class="alarm-summary" v-if="alarmsCollapsed">
        共 {{ activeAlarms.length }} 条报警 —
        <span class="alarm-summary-preview">{{ activeAlarms.slice(0, 2).map(a => a.message).join(' / ') }}</span>
        <template v-if="activeAlarms.length > 2"> ...</template>
      </div>
    </div>

    <!-- 卡片区：遥测 + 事件 -->
    <div class="grid">
      <div class="card">
        <h3 class="card-head">实时遥测</h3>
        <table class="table">
          <thead>
            <tr><th>点位</th><th>数值</th><th>时间</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in latestRows" :key="row.point">
              <td class="point-name">{{ row.point }}</td>
              <td class="point-value">{{ row.value }}</td>
              <td class="point-time">{{ row.ts }}</td>
            </tr>
            <tr v-if="latestRows.length === 0">
              <td colspan="3" class="empty-row">等待数据...</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card">
        <h3 class="card-head">事件日志</h3>
        <div class="event-list">
          <div v-for="(e, idx) in events" :key="idx" class="event-item"
            :class="{ 'event-alert': e.type === 'level-up' || e.type === 'level-down' || e.type === 'alarm' }">
            <span class="event-tag" :class="`tag-${e.type}`">{{ tagText(e) }}</span>
            <span class="event-msg">{{ e.msg }}</span>
            <span class="event-time">{{ formatEventTime(e.ts) }}</span>
          </div>
          <div v-if="events.length === 0" class="empty-row">暂无事件</div>
        </div>
      </div>
    </div>

    <!-- 诊断报告 -->
    <div class="report" v-if="prediction">
      <div class="report-header">
        <h3 class="report-title">诊断报告</h3>
        <span class="report-time">{{ reportTime }}</span>
      </div>

      <div class="report-body">
        <!-- 设备概览 -->
        <div class="report-section">
          <h4 class="section-title">设备概览</h4>
          <div class="section-grid">
            <div class="kv-item">
              <span class="kv-key">资产编号</span>
              <span class="kv-val">{{ assetId }}</span>
            </div>
            <div class="kv-item">
              <span class="kv-key">健康等级</span>
              <span class="kv-val" :class="`text-${prediction.health_level}`">{{ levelText }}</span>
            </div>
            <div class="kv-item">
              <span class="kv-key">健康分数</span>
              <span class="kv-val">{{ scoreText }} 分</span>
            </div>
            <div class="kv-item">
              <span class="kv-key">数据状态</span>
              <span class="kv-val">{{ dataAgeText }}</span>
            </div>
          </div>
        </div>

        <!-- 异常指标 -->
        <div class="report-section">
          <h4 class="section-title">
            异常指标
            <span class="section-badge" :class="abnormalCount ? 'badge-warn' : 'badge-ok'">
              {{ abnormalCount ? `${abnormalCount} 项异常` : '全部正常' }}
            </span>
          </h4>
          <div v-if="abnormalNodes.length" class="abnormal-list">
            <div v-for="(n, i) in abnormalNodes" :key="i" class="abnormal-item">
              <span class="abnormal-dot"></span>
              <div class="abnormal-text">
                <strong>{{ n.feature }}</strong>
                <span>{{ n.description }}</span>
              </div>
            </div>
          </div>
          <p v-else class="section-text">所有监测指标均在正常范围内，设备运转良好。</p>
        </div>

        <!-- 决策路径 -->
        <div class="report-section">
          <h4 class="section-title">决策路径</h4>
          <div class="path-steps">
            <div v-for="(n, i) in explainNodes" :key="i" class="path-step">
              <span class="path-num">{{ i + 1 }}</span>
              <span>{{ n.description }}</span>
            </div>
          </div>
        </div>

        <!-- 维护建议 -->
        <div class="report-section">
          <h4 class="section-title">维护建议</h4>
          <div class="advice-box" :class="`advice-${prediction.health_level}`">
            <p class="advice-text">{{ explainSummary }}</p>
            <ul v-if="abnormalActions.length" class="advice-actions">
              <li v-for="(a, i) in abnormalActions" :key="i">{{ a }}</li>
            </ul>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, reactive, ref, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import { fetchFlow, sseConnect, apiSimulateStart, apiCreateEvent, apiFetchEvents, apiFetchTrends, apiMe } from '../api'

const assetId = ref('PUMP-001')
const deviceList = ref(['PUMP-001'])
const scoreChartRef = ref(null)
const telemetryChartRef = ref(null)
let scoreChart = null
let telemetryChart = null

const POINT_LABELS = {
  rpm: '转速 (RPM)',
  load: '负载',
  vib_rms: '振动 RMS',
  temp_c: '温度 (°C)',
  motor_current_a: '电机电流 (A)',
  label_health_level: '健康等级',
}

const LEVEL_NAMES = { 0: '健康', 1: '注意', 2: '警告', 3: '危险' }

const flow = reactive({ mqtt_connected: false, model_loaded: false, last_message_age_s: null })

// 每个设备独立存储
const deviceLatest = reactive({})   // { asset_id: { point: data } }
const devicePredictions = reactive({})  // { asset_id: prediction }
const deviceEvents = reactive({})  // { asset_id: [...] }
const deviceLastLevel = reactive({})  // { asset_id: level }
const deviceAlarms = reactive({})  // { asset_id: [...] }
const deviceHealthHistory = reactive({})  // { asset_id: [...] }
const deviceAlarmHistory = reactive({})  // { asset_id: [...] }

// 初始化设备存储（按用户权限动态添加）
function initDevice(d) {
  if (!deviceLatest[d]) {
    deviceLatest[d] = {}
    devicePredictions[d] = null
    deviceEvents[d] = []
    deviceLastLevel[d] = null
    deviceAlarms[d] = []
    deviceHealthHistory[d] = []
    deviceAlarmHistory[d] = []
  }
}

function switchDevice(id) {
  assetId.value = id
  nextTick(() => {
    loadTrends(id)
    renderCharts()
  })
}

const replaying = ref(false)
const alarmsCollapsed = ref(false)
async function startReplay() {
  if (replaying.value) return
  replaying.value = true
  deviceList.value.forEach((d) => {
    deviceLastLevel[d] = null
    deviceEvents[d] = []
    deviceLatest[d] = {}
    devicePredictions[d] = null
  })
  try {
    await apiSimulateStart()
    pushEvent('prediction', '模拟数据流已启动，3 台设备同时观测...')
  } catch (e) {
    replaying.value = false
  }
  setTimeout(() => { replaying.value = false }, 600_000)
}

function deviceLevelText(id) {
  const p = devicePredictions[id]
  if (!p || p.health_level == null) return '--'
  return 'Lv' + p.health_level
}

function tagText(e) {
  if (e.type === 'level-up') return '恶化'
  if (e.type === 'level-down') return '恢复'
  if (e.type === 'alarm') return '报警'
  return e.type
}

function formatEventTime(ts) {
  return new Date(ts).toLocaleTimeString()
}

function pushEvent(type, msg, healthLevel, healthScore) {
  const now = Date.now()
  const evts = deviceEvents[assetId.value] || []
  const recent = evts.find(
    (e) => e.type === type && e.msg === msg && now - e.ts < 5000
  )
  if (recent) return

  evts.unshift({ type, msg, ts: now })
  if (evts.length > 30) evts.pop()

  apiCreateEvent(assetId.value, type, msg, healthLevel ?? null, healthScore ?? null).catch(() => {})
}

function alarmTypeText(ruleType) {
  const map = { threshold: '阈值', trend: '趋势', combination: '组合' }
  return map[ruleType] || ruleType
}

function formatAlarmTime(tsMs) {
  return new Date(tsMs).toLocaleTimeString()
}

/* ── 趋势数据加载 ── */

async function loadTrends(aId) {
  try {
    const data = await apiFetchTrends(aId)
    deviceHealthHistory[aId] = data.health_history || []
    deviceAlarmHistory[aId] = data.alarm_history || []
    // 从 alarm_history 初始化活跃报警 (最近 60s)
    const now = Date.now()
    deviceAlarms[aId] = (data.alarm_history || []).filter(
      (a) => now - a.ts_ms < 60_000
    )
  } catch { /* ignore */ }
}

/* ── ECharts 渲染 ── */

function buildScoreChartOption(healthHistory) {
  const times = healthHistory.map((h) => new Date(h.ts_ms).toLocaleTimeString())
  const scores = healthHistory.map((h) => h.health_score)
  return {
    tooltip: { trigger: 'axis' },
    grid: { top: 8, right: 16, bottom: 24, left: 48 },
    xAxis: {
      type: 'category',
      data: times,
      axisLabel: { fontSize: 10, color: '#86909c', rotate: times.length > 20 ? 45 : 0 },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      axisLabel: { fontSize: 10, color: '#86909c' },
      splitLine: { lineStyle: { color: '#f2f3f5' } },
    },
    series: [{
      data: scores,
      type: 'line',
      smooth: true,
      symbol: 'none',
      lineStyle: { color: '#1a73e8', width: 2 },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(26,115,232,0.12)' },
          { offset: 1, color: 'rgba(26,115,232,0.01)' },
        ]),
      },
      markLine: {
        silent: true,
        data: [
          { yAxis: 66, lineStyle: { color: '#f59e0b', type: 'dashed' } },
          { yAxis: 33, lineStyle: { color: '#ef4444', type: 'dashed' } },
        ],
        label: { fontSize: 10 },
      },
    }],
  }
}

function buildTelemetryChartOption(latestData, healthHistory) {
  // 从预测遥测快照提取关键指标值
  const times = healthHistory.map((h) => new Date(h.ts_ms).toLocaleTimeString())
  const scores = healthHistory.map((h) => h.health_score)
  const levels = healthHistory.map((h) => h.health_level)

  return {
    tooltip: { trigger: 'axis' },
    legend: {
      data: ['健康分数', '健康等级'],
      bottom: 0,
      textStyle: { fontSize: 10 },
    },
    grid: { top: 8, right: 16, bottom: 36, left: 48 },
    xAxis: {
      type: 'category',
      data: times,
      axisLabel: { fontSize: 10, color: '#86909c', rotate: times.length > 20 ? 45 : 0 },
    },
    yAxis: [
      {
        type: 'value',
        name: '分数',
        min: 0,
        max: 100,
        axisLabel: { fontSize: 10, color: '#86909c' },
        splitLine: { lineStyle: { color: '#f2f3f5' } },
      },
      {
        type: 'value',
        name: '等级',
        min: 0,
        max: 3,
        interval: 1,
        axisLabel: { fontSize: 10, color: '#86909c' },
      },
    ],
    series: [
      {
        name: '健康分数',
        data: scores,
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#1a73e8', width: 2 },
      },
      {
        name: '健康等级',
        data: levels,
        type: 'line',
        yAxisIndex: 1,
        step: 'end',
        symbol: 'none',
        lineStyle: { color: '#ef4444', width: 2, type: 'dotted' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(239,68,68,0.08)' },
            { offset: 1, color: 'rgba(239,68,68,0.0)' },
          ]),
        },
      },
    ],
  }
}

function renderCharts() {
  const aId = assetId.value
  const healthHistory = deviceHealthHistory[aId] || []

  if (scoreChartRef.value && healthHistory.length > 1) {
    if (!scoreChart) {
      scoreChart = echarts.init(scoreChartRef.value)
    }
    scoreChart.setOption(buildScoreChartOption(healthHistory), true)
  }

  if (telemetryChartRef.value && healthHistory.length > 1) {
    if (!telemetryChart) {
      telemetryChart = echarts.init(telemetryChartRef.value)
    }
    telemetryChart.setOption(buildTelemetryChartOption({}, healthHistory), true)
  }
}

function handleResize() {
  if (scoreChart) scoreChart.resize()
  if (telemetryChart) telemetryChart.resize()
}

/* ── computed ── */

const prediction = computed(() => devicePredictions[assetId.value])
const latest = computed(() => deviceLatest[assetId.value] || {})
const events = computed(() => deviceEvents[assetId.value] || [])
const activeAlarms = computed(() => deviceAlarms[assetId.value] || [])

const dataAgeText = computed(() => {
  if (flow.last_message_age_s == null) return '等待首次数据...'
  return flow.last_message_age_s < 5 ? '数据流入正常' : `静默 ${flow.last_message_age_s.toFixed(0)}s`
})

const latestRows = computed(() =>
  Object.values(latest.value)
    .map((p) => ({
      point: POINT_LABELS[p.point] || p.point,
      value: typeof p.value === 'number' ? p.value.toFixed(4) : String(p.value),
      ts: new Date(p.ts_ms).toLocaleTimeString(),
    }))
    .sort((a, b) => a.point.localeCompare(b.point))
)

const levelText = computed(() => {
  const lv = prediction.value?.health_level
  if (lv == null) return '--'
  return `Lv${lv} ${LEVEL_NAMES[lv] || ''}`
})

const levelClass = computed(() => {
  const lv = prediction.value?.health_level
  return lv != null ? `badge-${lv}` : ''
})

const scoreText = computed(() => {
  const s = prediction.value?.health_score
  return s != null ? s.toFixed(1) : '--'
})

const scoreColor = computed(() => {
  const s = prediction.value?.health_score ?? 100
  if (s > 66) return '#22c55e'
  if (s > 33) return '#f59e0b'
  return '#ef4444'
})

const scoreDasharray = computed(() => {
  const s = prediction.value?.health_score ?? 100
  const pct = s / 100
  const len = 2 * Math.PI * 52
  return `${len * pct} ${len * (1 - pct)}`
})

/* ── 决策路径中文化 ── */

const FEATURE_NAMES = {
  rpm_mean: '转速均值',
  load_mean: '负载均值',
  vib_rms_mean: '振动均值',
  temp_c_mean: '温度均值',
  motor_current_a_mean: '电流均值',
  vib_rms_std: '振动波动',
  temp_c_std: '温度波动',
  vib_rms_norm: '振动归一化值',
}

const FEATURE_DESCRIPTIONS = {
  rpm_mean: { high: '转速高于正常范围', low: '转速低于正常范围' },
  load_mean: { high: '负载偏高', low: '负载偏低' },
  vib_rms_mean: { high: '振动强度超标，可能存在轴承磨损或不对中', low: '振动处于正常水平' },
  temp_c_mean: { high: '温度偏高，可能润滑不足或过载', low: '温度处于正常范围' },
  motor_current_a_mean: { high: '电流偏高，电机负载加大或效率下降', low: '电流处于正常水平' },
  vib_rms_std: { high: '振动波动较大，运行不稳定', low: '振动波动正常' },
  temp_c_std: { high: '温度波动较大', low: '温度波动正常' },
  vib_rms_norm: { high: '转速归一化振动偏高', low: '归一化振动正常' },
}

const explainNodes = computed(() => {
  const raw = prediction.value?.explanation
  if (!raw) return []

  const sep = raw.includes('->') ? ' -> ' : (raw.includes('|') ? ' | ' : ' -> ')

  return raw.split(sep).map((seg) => {
    // 解析决策树格式: "vib_rms_mean > 2.351 (val=3.142)"
    const treeMatch = seg.match(/^(\S+)\s*(<=|>)\s*([\d.]+)\s*\(val=([\d.]+)\)/)
    if (treeMatch) {
      const [, feat, op, threshold, value] = treeMatch
      const name = FEATURE_NAMES[feat] || feat
      const tVal = parseFloat(threshold)
      const aVal = parseFloat(value)
      const isHigh = aVal > tVal
      const desc = FEATURE_DESCRIPTIONS[feat]

      let description = ''
      if (desc) {
        description = isHigh ? desc.high : desc.low
      }
      if (op === '>' && isHigh) {
        description = `${name} ${aVal.toFixed(2)} > 阈值 ${tVal.toFixed(2)}，${description}`
      } else if (op === '<=' && !isHigh) {
        description = `${name} ${aVal.toFixed(2)} ≤ 阈值 ${tVal.toFixed(2)}，${description}`
      } else {
        description = `${name} ${aVal.toFixed(2)} ${op} ${tVal.toFixed(2)}，${description}`
      }
      return { feature: name, description, abnormal: op === '>' && isHigh }
    }

    // 解析 XGBoost/LightGBM 格式: "vib_rms_mean>偏高↑(val=3.21, z=+2.3, imp=0.23)"
    const boostMatch = seg.match(/^(\S+)>(偏高↑|偏低↓|略高|略低|正常)\(val=([\d.]+),\s*z=([+\-\d.]+),\s*imp=([\d.]+)\)/)
    if (boostMatch) {
      const [, feat, direction, value, z, imp] = boostMatch
      const name = FEATURE_NAMES[feat] || feat
      const aVal = parseFloat(value)
      const desc = FEATURE_DESCRIPTIONS[feat]
      const isAbnormal = direction.includes('偏高') || direction.includes('偏低')

      let description = ''
      if (desc && direction.includes('偏高')) {
        description = desc.high
      } else if (desc && direction.includes('偏低')) {
        description = desc.low
      }
      const zLabel = parseFloat(z) > 0 ? `(偏离${direction.replace(/[↑↓]/,'')}，z=${z})` : ''
      description = `${name}=${aVal.toFixed(2)} ${direction} ${zLabel}，重要性=${parseFloat(imp).toFixed(2)}。${description}`
      return { feature: name, description, abnormal: isAbnormal }
    }

    return { feature: seg, description: seg, abnormal: false }
  })
})

const explainSummary = computed(() => {
  const lv = prediction.value?.health_level
  const names = ['正常运转，各项指标均在健康范围内。', '设备状态需要关注，建议定期检查关键指标趋势。', '设备存在明显异常，建议尽快安排维护检查。', '设备处于危险状态，存在故障风险，请立即停机检查。']
  return lv != null ? names[lv] || '' : ''
})

/* ── 诊断报告 ── */

const reportTime = computed(() => new Date().toLocaleString())

const abnormalNodes = computed(() => explainNodes.value.filter((n) => n.abnormal))
const abnormalCount = computed(() => abnormalNodes.value.length)

const abnormalActions = computed(() => {
  return abnormalNodes.value.map((n) => {
    const map = {
      '振动均值': '检查轴承状态、对中情况，必要时做振动频谱分析',
      '温度均值': '检查润滑系统、散热通道，确认负载是否正常',
      '电流均值': '检查电机绝缘、传动效率，排查机械卡阻',
      '振动波动': '检查运行平稳性，可能存在间歇性冲击',
      '温度波动': '检查冷却系统稳定性，监控温度变化趋势',
      '振动归一化值': '检查转速与振动关系，排查转子不平衡',
    }
    return map[n.feature] || `关注「${n.feature}」趋势，安排专项巡检`
  })
})

const probaItems = computed(() => {
  const p = prediction.value?.proba
  if (!Array.isArray(p) || p.length < 4) {
    return [0, 1, 2, 3].map((i) => ({ label: `Lv${i} ${LEVEL_NAMES[i]}`, pct: 0 }))
  }
  return p.map((v, i) => ({
    label: `Lv${i} ${LEVEL_NAMES[i]}`,
    pct: Number(v) * 100,
  }))
})

/* ── lifecycle ── */

let stop = null
let lastFlowFetchMs = 0

onMounted(async () => {
  // 加载用户设备权限
  let allowedDevices = ['PUMP-001']
  try {
    const me = await apiMe()
    if (me.user?.devices) {
      const devs = me.user.devices
      if (devs.includes('*')) {
        allowedDevices = ['PUMP-001', 'PUMP-002', 'PUMP-003']
      } else {
        allowedDevices = devs.filter((d) => d !== '*')
      }
    }
  } catch { /* ignore */ }
  deviceList.value = allowedDevices
  allowedDevices.forEach((d) => initDevice(d))
  assetId.value = allowedDevices[0] || 'PUMP-001'

  try {
    const f = await fetchFlow()
    Object.assign(flow, f)
  } catch { /* ignore */ }

  // 加载最近 10 分钟内的历史事件
  try {
    const res = await apiFetchEvents(assetId.value, 50)
    if (res.events) {
      const cutoff = Date.now() - 10 * 60 * 1000
      deviceEvents[assetId.value] = res.events
        .filter((e) => new Date(e.created_at).getTime() > cutoff)
        .map((e) => ({
          type: e.type,
          msg: e.message,
          ts: new Date(e.created_at).getTime(),
        }))
    }
  } catch { /* ignore */ }

  // 加载初始趋势
  await loadTrends(assetId.value)
  nextTick(() => renderCharts())

  window.addEventListener('resize', handleResize)

  stop = sseConnect(async (evt) => {
    if (evt.type === 'telemetry') {
      const p = evt.data
      if (!p || !p.asset_id) return
      const aId = p.asset_id
      if (!allowedDevices.includes(aId)) return  // 权限过滤
      initDevice(aId)
      deviceLatest[aId][p.point] = p
    }

    if (evt.type === 'prediction') {
      const hr = evt.data
      if (!hr || !hr.asset_id) return
      const aId = hr.asset_id
      if (!allowedDevices.includes(aId)) return  // 权限过滤
      initDevice(aId)
      devicePredictions[aId] = hr

      // 追加健康历史
      if (deviceHealthHistory[aId]) {
        deviceHealthHistory[aId].push({
          ts_ms: hr.ts_ms,
          health_level: hr.health_level,
          health_score: hr.health_score,
        })
        if (deviceHealthHistory[aId].length > 200) {
          deviceHealthHistory[aId] = deviceHealthHistory[aId].slice(-200)
        }
      }

      const newLevel = hr.health_level
      const lastLevel = deviceLastLevel[aId]
      if (lastLevel !== null && newLevel !== lastLevel) {
        const prevId = assetId.value
        assetId.value = aId
        const dir = newLevel > lastLevel ? 'level-up' : 'level-down'
        const oldName = LEVEL_NAMES[lastLevel] || `Lv${lastLevel}`
        const newName = LEVEL_NAMES[newLevel] || `Lv${newLevel}`
        pushEvent(dir, `${oldName} → ${newName}（${Number(hr.health_score).toFixed(1)} 分）`, newLevel, Number(hr.health_score))
        assetId.value = prevId
      }
      deviceLastLevel[aId] = newLevel

      // 实时更新图表 (每 3 次预测渲染一次，避免过度刷新)
      const counter = (deviceHealthHistory[aId]?._renderCounter || 0) + 1
      if (deviceHealthHistory[aId]) deviceHealthHistory[aId]._renderCounter = counter
      if (aId === assetId.value && counter % 3 === 0) {
        nextTick(() => renderCharts())
      }
    }

    if (evt.type === 'alarm') {
      const alarm = evt.data
      if (!alarm || !alarm.asset_id) return
      const aId = alarm.asset_id
      if (!allowedDevices.includes(aId)) return
      initDevice(aId)
      // 添加到活跃报警，去重
      const existing = deviceAlarms[aId].find(
        (a) => a.rule_name === alarm.rule_name && Date.now() - a.ts_ms < 30_000
      )
      if (!existing) {
        deviceAlarms[aId].unshift(alarm)
        if (deviceAlarms[aId].length > 20) deviceAlarms[aId].pop()
        // 也添加到事件列表
        if (aId === assetId.value) {
          pushEvent('alarm', `[${alarm.severity}] ${alarm.message}`, null, null)
        }
      }
      // 60s 后自动清除活跃报警
      setTimeout(() => {
        const idx = deviceAlarms[aId].indexOf(alarm)
        if (idx >= 0) deviceAlarms[aId].splice(idx, 1)
      }, 60_000)
    }

    if (evt.type === 'error') {
      // SSE 断连，静默忽略
    }

    const nowMs = Date.now()
    if (nowMs - lastFlowFetchMs > 1000) {
      lastFlowFetchMs = nowMs
      try {
        const f = await fetchFlow()
        Object.assign(flow, f)
      } catch { /* ignore */ }
    }
  })
})

onBeforeUnmount(() => {
  if (stop) stop()
  if (scoreChart) { scoreChart.dispose(); scoreChart = null }
  if (telemetryChart) { telemetryChart.dispose(); telemetryChart = null }
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
.dashboard {
  padding: 20px 24px;
  max-width: 1280px;
  margin: 0 auto;
}

[v-cloak] { display: none; }

/* ── Trends Section ── */

.trends-section {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}

.trend-card {
  background: #fff;
  border: 1px solid #e8ecf1;
  border-radius: 10px;
  padding: 18px 20px 12px;
}

.chart-box {
  width: 100%;
  height: 220px;
}

/* ── Alarms Section ── */

.alarms-section {
  background: #fff;
  border: 1px solid #fecaca;
  border-radius: 10px;
  margin-bottom: 16px;
  overflow: hidden;
}

.alarm-header {
  padding: 12px 20px;
  border-bottom: 1px solid #fee2e2;
  background: #fef2f2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  user-select: none;
}

.alarm-header:hover {
  background: #fee2e2;
}

.alarm-collapse-icon {
  font-size: 14px;
  color: #b91c1c;
  transition: transform 0.25s ease;
  line-height: 1;
}

.alarm-collapse-icon.collapsed {
  transform: rotate(-90deg);
}

.alarm-head-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #b91c1c;
  margin: 0;
}

.alarm-list {
  display: flex;
  flex-direction: column;
  max-height: 800px;
  overflow: hidden;
  transition: max-height 0.3s ease;
}

.alarm-list.collapsed {
  max-height: 0;
}

.alarm-item {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 10px 20px;
  font-size: 13px;
  border-bottom: 1px solid #fef2f2;
}

.alarm-item:last-child {
  border-bottom: none;
}

.alarm-warning {
  background: #fffbeb;
  color: #92400e;
}

.alarm-critical {
  background: #fef2f2;
  color: #991b1b;
}

.alarm-type-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
  flex-shrink: 0;
}

.alarm-warning .alarm-type-badge {
  background: #fde68a;
  color: #92400e;
}

.alarm-critical .alarm-type-badge {
  background: #fecaca;
  color: #991b1b;
}

.alarm-msg {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.alarm-time {
  font-size: 11px;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
  opacity: 0.7;
}

.alarm-summary {
  padding: 8px 20px;
  font-size: 12px;
  color: #b91c1c;
  background: #fef2f2;
  border-top: 1px solid #fee2e2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.alarm-summary-preview {
  color: #92400e;
}

/* ── Status Bar ── */

.status-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
  padding: 10px 16px;
  background: #fff;
  border: 1px solid #e8ecf1;
  border-radius: 10px;
  font-size: 13px;
  color: #4e5969;
}

.status-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

.muted { color: #86909c; }

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot-green { background: #22c55e; }
.dot-red   { background: #ef4444; }

.status-spacer { flex: 1; }

.btn-replay {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 14px;
  background: #fff;
  border: 1px solid #dde2e8;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  color: #4e5969;
  cursor: pointer;
  transition: all 0.2s ease-in-out;
}

.btn-replay:hover {
  background: #fef2f2;
  border-color: #fca5a5;
  color: #dc2626;
}

.btn-replay:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background: #f8f9fb;
  border-color: #e8ecf1;
  color: #c9cdd4;
}

/* ── Device Tabs ── */

.device-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.device-tab {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 18px;
  background: #fff;
  border: 1px solid #e8ecf1;
  border-radius: 10px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease-in-out;
}

.device-tab:hover {
  border-color: #c0c8d4;
  background: #f8f9fb;
}

.tab-active {
  border-color: #1a73e8;
  background: #f0f6ff;
  box-shadow: 0 0 0 2px rgba(26, 115, 232, 0.12);
}

.tab-name {
  font-weight: 600;
  color: #1d2129;
}

.tab-level {
  font-size: 11px;
  font-weight: 700;
  padding: 1px 8px;
  border-radius: 999px;
}

.tab-lv-0  { background: #dcfce7; color: #15803d; }
.tab-lv-1  { background: #fef3c7; color: #b45309; }
.tab-lv-2  { background: #fee2e2; color: #b91c1c; }
.tab-lv-3  { background: #fce7f3; color: #9d174d; }
.tab-lv--1 { background: #f2f3f5; color: #86909c; }

/* ════════════ Prediction Hero ════════════ */

.prediction-hero {
  background: #fff;
  border: 1px solid #e8ecf1;
  border-radius: 12px;
  margin-bottom: 16px;
  overflow: hidden;
  transition: box-shadow 0.2s ease-in-out;
}

.prediction-hero:hover {
  box-shadow: 0 1px 4px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.04);
}

.hero-inner {
  display: flex;
  align-items: stretch;
  padding: 28px 32px;
  gap: 40px;
}

.hero-visual {
  display: flex;
  align-items: center;
  gap: 32px;
  flex-shrink: 0;
}

/* score ring */
.score-ring-wrap {
  position: relative;
  width: 120px;
  height: 120px;
  flex-shrink: 0;
}

.score-ring {
  width: 120px;
  height: 120px;
  transform: rotate(-90deg);
}

.ring-bg {
  fill: none;
  stroke: #f2f3f5;
  stroke-width: 7;
}

.ring-fill {
  fill: none;
  stroke-width: 7;
  stroke-linecap: round;
  transition: stroke-dasharray 0.6s ease-in-out, stroke 0.4s ease-in-out;
}

.ring-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.ring-value {
  font-size: 28px;
  font-weight: 700;
  color: #1d2129;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.ring-unit {
  font-size: 12px;
  color: #86909c;
  margin-top: 2px;
}

/* level badge */
.level-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.level-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 10px 28px;
  border-radius: 10px;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.3px;
  min-width: 140px;
  text-align: center;
}

.badge-0 { background: #dcfce7; color: #15803d; }
.badge-1 { background: #fef3c7; color: #b45309; }
.badge-2 { background: #fee2e2; color: #b91c1c; }
.badge-3 { background: #fce7f3; color: #9d174d; }

.level-label {
  font-size: 12px;
  color: #86909c;
}

/* detail — probability chart */
.hero-detail {
  flex: 1;
  min-width: 0;
  padding-left: 40px;
  border-left: 1px solid #f2f3f5;
}

.detail-title {
  font-size: 13px;
  font-weight: 600;
  color: #4e5969;
  margin: 0 0 20px 0;
}

.proba-chart {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.proba-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.proba-label {
  width: 72px;
  font-size: 12px;
  font-weight: 500;
  flex-shrink: 0;
  text-align: right;
}
.proba-label-0 { color: #15803d; }
.proba-label-1 { color: #b45309; }
.proba-label-2 { color: #b91c1c; }
.proba-label-3 { color: #9d174d; }

.proba-track {
  flex: 1;
  height: 10px;
  background: #f2f3f5;
  border-radius: 5px;
  overflow: hidden;
}

.proba-fill {
  height: 100%;
  border-radius: 5px;
  transition: width 0.5s ease-in-out;
}
.proba-fill-0 { background: #22c55e; }
.proba-fill-1 { background: #f59e0b; }
.proba-fill-2 { background: #ef4444; }
.proba-fill-3 { background: #ec4899; }

.proba-val {
  width: 52px;
  font-size: 13px;
  font-weight: 600;
  color: #1d2129;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
  text-align: right;
}

/* hero foot — diagnosis timeline */
.hero-foot {
  border-top: 1px solid #f2f3f5;
  padding: 18px 32px 20px;
  background: #fafbfc;
}

.foot-label {
  font-size: 11px;
  color: #86909c;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.diagnosis-timeline {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
}

.diag-node {
  display: flex;
  gap: 14px;
}

.diag-node + .diag-node {
  margin-top: 2px;
}

/* left: step + connector */
.diag-left {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 28px;
  padding-top: 2px;
}

.diag-step {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: #e8ecf1;
  color: #4e5969;
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s ease-in-out;
}

.diag-step-warn {
  background: #dc2626;
  color: #fff;
}

.diag-line {
  flex: 1;
  width: 2px;
  min-height: 16px;
  background: #e8ecf1;
  margin: 3px 0;
}

/* right: content */
.diag-right {
  flex: 1;
  padding: 3px 0 14px;
}

.diag-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 4px;
}

.diag-feat {
  font-size: 14px;
  font-weight: 600;
  color: #1d2129;
}

.diag-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 8px;
  border-radius: 999px;
  background: #fee2e2;
  color: #dc2626;
}

.diag-badge-ok {
  background: #dcfce7;
  color: #15803d;
}

.diag-desc {
  font-size: 12px;
  color: #4e5969;
  line-height: 1.5;
  max-width: 52ch;
}

.diag-abnormal .diag-right {
  background: #fef2f2;
  margin: 0 -12px;
  padding: 8px 12px 14px;
  border-radius: 8px;
  border: 1px solid #fecaca;
}

.explain-summary {
  margin-top: 10px;
  padding-top: 12px;
  border-top: 1px dashed #e5e8eb;
  font-size: 13px;
  color: #1a73e8;
  font-weight: 500;
  line-height: 1.5;
}

/* ════════════ Cards ════════════ */

.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

@media (max-width: 900px) {
  .grid { grid-template-columns: 1fr; }
  .trends-section { grid-template-columns: 1fr; }
  .dashboard { padding: 12px 14px; }

  .hero-inner {
    flex-direction: column;
    align-items: center;
    padding: 20px;
    gap: 24px;
  }

  .hero-detail {
    border-left: none;
    border-top: 1px solid #f2f3f5;
    padding-left: 0;
    padding-top: 20px;
  }

  .hero-foot {
    padding: 12px 16px 16px;
  }

  .explain-flow {
    flex-direction: column;
    gap: 12px;
  }

  .explain-node + .explain-node {
    margin-left: 0;
  }

  .explain-node + .explain-node::before {
    display: none;
  }
}

.card {
  background: #fff;
  border: 1px solid #e8ecf1;
  border-radius: 10px;
  padding: 18px 20px;
  transition: box-shadow 0.2s ease-in-out;
}

.card:hover {
  box-shadow: 0 1px 4px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.04);
}

.card-head {
  font-size: 14px;
  font-weight: 600;
  color: #1d2129;
  margin: 0 0 14px 0;
}

/* table */
.table { width: 100%; border-collapse: collapse; }

.table th {
  font-size: 12px;
  font-weight: 500;
  color: #86909c;
  text-align: left;
  padding: 0 8px 8px;
  border-bottom: 1px solid #f2f3f5;
}

.table td {
  font-size: 13px;
  color: #1d2129;
  padding: 7px 8px;
  border-bottom: 1px solid #fafbfc;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.point-name  { color: #4e5969; }
.point-value { font-variant-numeric: tabular-nums; font-weight: 500; }
.point-time  { color: #86909c; font-size: 12px; }

.empty-row {
  color: #c9cdd4;
  font-size: 13px;
  text-align: center;
  padding: 24px 8px !important;
}

/* events */
.event-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 280px;
  overflow-y: auto;
}

.event-item {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 6px 8px;
  font-size: 13px;
  border-radius: 6px;
  transition: background 0.2s ease-in-out;
}

.event-item:hover {
  background: #f8f9fb;
}

.event-alert {
  background: #fef2f2;
  border: 1px solid #fecaca;
}

.event-alert:hover {
  background: #fee2e2;
}

.event-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
  flex-shrink: 0;
  letter-spacing: 0.3px;
}

.tag-level-up,
.tag-level-down { background: #dc2626; color: #fff; }
.tag-alarm      { background: #fef3c7; color: #b45309; }
.tag-error       { background: #fee2e2; color: #b91c1c; }
.tag-prediction  { background: #dbeafe; color: #1d4ed8; }

.event-msg {
  color: #4e5969;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.event-time {
  font-size: 11px;
  color: #86909c;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}

/* ════════════ Report ════════════ */

.report {
  margin-top: 16px;
  background: #fff;
  border: 1px solid #e8ecf1;
  border-radius: 10px;
  overflow: hidden;
}

.report-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  border-bottom: 1px solid #f2f3f5;
}

.report-title {
  font-size: 16px;
  font-weight: 700;
  color: #1d2129;
  margin: 0;
}

.report-time {
  font-size: 12px;
  color: #86909c;
}

.report-body {
  padding: 20px 24px 24px;
}

.report-section {
  margin-bottom: 20px;
}

.report-section:last-child {
  margin-bottom: 0;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #1d2129;
  margin: 0 0 12px 0;
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-badge {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 10px;
  border-radius: 999px;
}

.badge-warn { background: #fef3c7; color: #b45309; }
.badge-ok   { background: #dcfce7; color: #15803d; }

.section-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}

.kv-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 12px;
  background: #f8f9fb;
  border-radius: 6px;
}

.kv-key {
  font-size: 11px;
  color: #86909c;
}

.kv-val {
  font-size: 14px;
  font-weight: 600;
  color: #1d2129;
}

.text-0 { color: #15803d; }
.text-1 { color: #b45309; }
.text-2 { color: #b91c1c; }
.text-3 { color: #9d174d; }

.section-text {
  font-size: 13px;
  color: #4e5969;
  margin: 0;
}

/* abnormal list */
.abnormal-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.abnormal-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 14px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
}

.abnormal-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #dc2626;
  margin-top: 5px;
  flex-shrink: 0;
}

.abnormal-text {
  font-size: 13px;
  color: #4e5969;
  line-height: 1.5;
}

.abnormal-text strong {
  color: #b91c1c;
  margin-right: 8px;
}

/* path steps */
.path-steps {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.path-step {
  display: flex;
  align-items: baseline;
  gap: 10px;
  font-size: 13px;
  color: #4e5969;
  padding: 6px 0;
}

.path-num {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #e8ecf1;
  color: #4e5969;
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

/* advice */
.advice-box {
  padding: 14px 18px;
  border-radius: 8px;
  border: 1px solid;
}

.advice-0 { background: #f0fdf4; border-color: #bbf7d0; }
.advice-1 { background: #fefce8; border-color: #fde68a; }
.advice-2 { background: #fef2f2; border-color: #fecaca; }
.advice-3 { background: #fdf2f8; border-color: #fbcfe8; }

.advice-text {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 8px 0;
}

.advice-0 .advice-text { color: #15803d; }
.advice-1 .advice-text { color: #b45309; }
.advice-2 .advice-text { color: #b91c1c; }
.advice-3 .advice-text { color: #9d174d; }

.advice-actions {
  margin: 0;
  padding-left: 20px;
}

.advice-actions li {
  font-size: 13px;
  color: #4e5969;
  line-height: 1.7;
}

@media (max-width: 900px) {
  .report-header {
    padding: 12px 14px;
  }
  .report-body {
    padding: 14px;
  }
  .section-grid {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
