<template>
  <div class="report-page" v-cloak>
    <h2 class="page-title">诊断报告</h2>

    <div v-if="loading" class="loading-msg">加载诊断数据...</div>
    <div v-if="error" class="err-msg">{{ error }}</div>

    <div class="report-grid" v-if="!loading && !error">
      <div v-for="r in reports" :key="r.asset_id" class="report-card" :class="'card-lv-' + (r.health_level ?? -1)">
        <!-- 卡片头 -->
        <div class="card-top">
          <div class="card-device">
            <h3>{{ r.asset_id }}</h3>
            <span class="card-lv-badge" :class="'lv-bg-' + (r.health_level ?? -1)">
              {{ levelText(r.health_level) }}
            </span>
          </div>
          <div class="card-score">
            <svg class="mini-ring" viewBox="0 0 60 60">
              <circle class="mini-ring-bg" cx="30" cy="30" r="25" />
              <circle class="mini-ring-fill" cx="30" cy="30" r="25"
                :stroke-dasharray="(r.health_score || 0) * 1.57 + ' 157'"
                :stroke="scoreColor(r.health_score)" />
            </svg>
            <span class="mini-score-num">{{ r.health_score != null ? r.health_score.toFixed(1) : '--' }}</span>
          </div>
        </div>

        <!-- 遥测概览 -->
        <div class="card-telemetry" v-if="r.latest_telemetry && Object.keys(r.latest_telemetry).length">
          <div class="mini-row" v-for="(v, k) in r.latest_telemetry" :key="k">
            <span class="mini-point">{{ pointLabel(k) }}</span>
            <span class="mini-val" :class="{ 'val-warn': isAbnormal(k, v) }">{{ fmtVal(v) }}</span>
          </div>
        </div>

        <!-- 诊断依据 -->
        <div class="card-diag" v-if="r.explain_nodes && r.explain_nodes.length">
          <span class="diag-label">诊断依据</span>
          <div class="diag-list">
            <div v-for="(n, i) in r.explain_nodes.slice(0, 3)" :key="i" class="diag-item"
              :class="{ 'diag-warn': n.abnormal }">
              <span class="diag-step">{{ i + 1 }}</span>
              <span class="diag-feat">{{ n.feature }}</span>
              <span class="diag-desc">{{ n.description }}</span>
            </div>
          </div>
        </div>

        <!-- 报警 -->
        <div class="card-alarms" v-if="r.active_alarms && r.active_alarms.length">
          <span class="alarm-label">活跃报警</span>
          <div v-for="(a, i) in r.active_alarms.slice(0, 2)" :key="i" class="mini-alarm" :class="'mini-alarm-' + a.severity">
            {{ a.message }}
          </div>
        </div>

        <!-- 维护建议 -->
        <div class="card-advice" v-if="r.advice">
          <span class="advice-label">维护建议</span>
          <p class="advice-text">{{ r.advice }}</p>
        </div>
      </div>

      <div v-if="reports.length === 0" class="empty-msg">暂无设备数据</div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiMe, fetchFlow } from '../api'

const router = useRouter()
const reports = ref([])
const loading = ref(true)
const error = ref('')

const LEVEL_NAMES = { 0: '健康', 1: '注意', 2: '警告', 3: '危险' }
const LEVEL_COLORS = { 0: '#10b981', 1: '#f59e0b', 2: '#ef4444', 3: '#8b5cf6' }
const POINT_LABELS = {
  rpm: '转速', load: '负载', vib_rms: '振动 RMS',
  temp_c: '温度', motor_current_a: '电机电流',
}

function levelText(lv) {
  return LEVEL_NAMES[lv] ?? '未知'
}

function scoreColor(s) {
  if (s == null) return '#cbd5e1'
  if (s >= 80) return '#10b981'
  if (s >= 60) return '#f59e0b'
  if (s >= 40) return '#ef4444'
  return '#8b5cf6'
}

function pointLabel(k) {
  return POINT_LABELS[k] || k
}

function fmtVal(v) {
  if (v == null) return '--'
  if (typeof v === 'number') {
    if (Math.abs(v) < 0.01) return '0'
    if (Math.abs(v) < 10) return v.toFixed(3)
    if (Math.abs(v) < 100) return v.toFixed(2)
    return v.toFixed(1)
  }
  return String(v)
}

const ABNORMAL_RANGES = {
  vib_rms: { max: 4.5 },
  temp_c: { max: 85 },
  motor_current_a: { max: 12 },
}

function isAbnormal(k, v) {
  const range = ABNORMAL_RANGES[k]
  if (!range || v == null) return false
  return range.max != null && v > range.max
}

const ADVICE_MAP = {
  0: '设备运行状态良好。按计划执行常规巡检，保持当前运行参数。',
  1: '设备出现轻微异常趋势，建议缩短巡检周期，关注振动和温度变化趋势。',
  2: '设备存在明显异常指标，建议安排近期停机检查，重点排查轴承、密封件磨损。',
  3: '设备处于危险状态！请立即停机检查，排查电机过载、轴承失效、转子不平衡等故障。',
}

function parseExplanation(explanation) {
  if (!explanation) return []
  // Split by " -> " for decision-tree path or feature-importance chain
  const parts = explanation.split(' -> ').filter(Boolean)
  return parts.map((seg) => {
    // Extract feature name (first token before space/symbol)
    const feature = seg.split(/[ <=>(\u2191\u2193]/)[0] || ''
    const abnormal = /偏高|偏低|↑|↓|>/.test(seg)
    return { feature, description: seg, abnormal }
  })
}

onMounted(async () => {
  try {
    // auth check
    const me = await apiMe()
    const userDevices = me.user?.devices || []
    const deviceList = userDevices.includes('*')
      ? ['PUMP-001', 'PUMP-002', 'PUMP-003', 'PUMP-004', 'PUMP-005']
      : userDevices.filter(d => d !== '*')

    if (deviceList.length === 0) {
      loading.value = false
      return
    }

    // Fetch state for each device
    const results = []
    for (const assetId of deviceList) {
      try {
        const res = await fetch(
          `${getApiBase()}/api/state?asset_id=${encodeURIComponent(assetId)}`,
          { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } }
        )
        const data = await res.json()
        if (res.ok) {
          const health = (data.health_latest || {})[assetId] || {}
          const telemetryRaw = (data.telemetry_latest || {})[assetId] || {}
          // Convert {point: {value, ...}} → {point_label: value}
          const telemetry = {}
          for (const [k, v] of Object.entries(telemetryRaw)) {
            telemetry[k] = (v && typeof v === 'object') ? v.value : v
          }
          const adviceLv = health.health_level != null ? health.health_level : -1
          results.push({
            asset_id: assetId,
            health_level: health.health_level ?? null,
            health_score: health.health_score ?? null,
            latest_telemetry: telemetry,
            explain_nodes: parseExplanation(health.explanation || ''),
            active_alarms: (data.active_alarms || []),
            advice: ADVICE_MAP[adviceLv] || '数据不足，无法生成维护建议。请确保设备正在运行且数据正常推送。',
            updated_at: health.ts_ms || null,
          })
        }
      } catch {
        // skip failed device
      }
    }
    reports.value = results
  } catch {
    router.replace('/login')
  } finally {
    loading.value = false
  }
})

function getApiBase() {
  const envBase = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '')
  if (envBase) return envBase
  const loc = window.location
  const port = String(loc.port || '')
  if (port && port !== '5173') return `${loc.protocol}//${loc.hostname}:5000`
  return ''
}
</script>

<style scoped>
.report-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px;
}

.page-title {
  font-size: 20px;
  font-weight: 700;
  color: #1d2129;
  margin: 0 0 20px;
}

.loading-msg { font-size: 14px; color: #86909c; }
.err-msg { padding: 10px 14px; background: #fee2e2; color: #b91c1c; border-radius: 8px; margin-bottom: 16px; font-size: 13px; }
.empty-msg { font-size: 14px; color: #86909c; text-align: center; padding: 40px 0; }

/* Grid */
.report-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}

/* Card */
.report-card {
  background: #fff;
  border: 1px solid #e8ecf1;
  border-radius: 10px;
  overflow: hidden;
}

.report-card.card-lv--1 { border-color: #e8ecf1; }
.report-card.card-lv-0  { border-color: #d1fae5; }
.report-card.card-lv-1  { border-color: #fde68a; }
.report-card.card-lv-2  { border-color: #fecaca; }
.report-card.card-lv-3  { border-color: #ddd6fe; }

/* Top */
.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 18px 12px;
  border-bottom: 1px solid #f2f3f5;
}

.card-device h3 {
  font-size: 16px;
  font-weight: 700;
  color: #1d2129;
  margin: 0 0 4px;
}

.card-lv-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 10px;
  border-radius: 999px;
}

.lv-bg--1 { background: #f2f3f5; color: #86909c; }
.lv-bg-0  { background: #d1fae5; color: #065f46; }
.lv-bg-1  { background: #fef3c7; color: #92400e; }
.lv-bg-2  { background: #fee2e2; color: #991b1b; }
.lv-bg-3  { background: #ede9fe; color: #5b21b6; }

/* Mini ring */
.card-score {
  position: relative;
  width: 60px; height: 60px;
  display: flex; align-items: center; justify-content: center;
}

.mini-ring {
  position: absolute;
  width: 60px; height: 60px;
  transform: rotate(-90deg);
}

.mini-ring-bg {
  fill: none;
  stroke: #f2f3f5;
  stroke-width: 5;
}

.mini-ring-fill {
  fill: none;
  stroke-width: 5;
  stroke-linecap: round;
}

.mini-score-num {
  font-size: 16px;
  font-weight: 700;
  color: #1d2129;
}

/* Telemetry */
.card-telemetry {
  padding: 10px 18px;
  border-bottom: 1px solid #f2f3f5;
}

.mini-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 3px 0;
  font-size: 12px;
}

.mini-point { color: #86909c; }
.mini-val { color: #4e5969; font-weight: 500; font-variant-numeric: tabular-nums; }
.val-warn { color: #ef4444; font-weight: 600; }

/* Diagnosis */
.card-diag {
  padding: 12px 18px;
  border-bottom: 1px solid #f2f3f5;
}

.diag-label {
  font-size: 11px;
  font-weight: 600;
  color: #86909c;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
  display: block;
}

.diag-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.diag-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.diag-step {
  width: 18px; height: 18px;
  border-radius: 50%;
  background: #f2f3f5;
  display: flex; align-items: center; justify-content: center;
  font-size: 10px; font-weight: 700;
  color: #86909c;
  flex-shrink: 0;
}

.diag-feat {
  font-weight: 600;
  color: #4e5969;
  white-space: nowrap;
}

.diag-desc {
  color: #86909c;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.diag-item.diag-warn .diag-step {
  background: #fee2e2;
  color: #b91c1c;
}

.diag-item.diag-warn .diag-feat {
  color: #b91c1c;
}

/* Alarms */
.card-alarms {
  padding: 10px 18px;
  border-bottom: 1px solid #f2f3f5;
}

.alarm-label {
  font-size: 11px;
  font-weight: 600;
  color: #b91c1c;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
  display: block;
}

.mini-alarm {
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 4px;
  margin-bottom: 4px;
}

.mini-alarm-warning  { background: #fef3c7; color: #92400e; }
.mini-alarm-critical { background: #fee2e2; color: #991b1b; }

/* Advice */
.card-advice {
  padding: 12px 18px;
}

.advice-label {
  font-size: 11px;
  font-weight: 600;
  color: #10b981;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
  display: block;
}

.advice-text {
  font-size: 12px;
  color: #4e5969;
  line-height: 1.6;
  margin: 0;
}
</style>
