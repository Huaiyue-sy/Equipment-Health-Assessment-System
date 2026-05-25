function normalizeBaseUrl(s) {
  if (!s) return ''
  return String(s).replace(/\/$/, '')
}

function apiUrl(path) {
  const envBase = normalizeBaseUrl(import.meta.env.VITE_API_BASE)
  if (envBase) return `${envBase}${path}`
  const loc = window.location
  const port = String(loc.port || '')
  if (port && port !== '5173') {
    return `${loc.protocol}//${loc.hostname}:5000${path}`
  }
  return path
}

function authHeaders() {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/* ── Auth ── */

export async function apiRegister(username, email, password) {
  const res = await fetch(apiUrl('/api/auth/register'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, email, password }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || '注册失败')
  return data
}

export async function apiLogin(username, password) {
  const res = await fetch(apiUrl('/api/auth/login'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || '登录失败')
  return data
}

export async function apiMe() {
  const res = await fetch(apiUrl('/api/auth/me'), { headers: authHeaders() })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || '认证失败')
  return data
}

/* ── Data ── */

export function sseConnect(onEvent) {
  const token = localStorage.getItem('token')
  if (!token) {
    onEvent({ type: 'error', data: { ok: false } })
    return () => {}
  }
  const es = new EventSource(apiUrl(`/api/stream?token=${encodeURIComponent(token)}`))

  es.addEventListener('hello', (e) => {
    onEvent({ type: 'hello', data: safeJson(e.data) })
  })
  es.addEventListener('telemetry', (e) => {
    onEvent({ type: 'telemetry', data: safeJson(e.data) })
  })
  es.addEventListener('prediction', (e) => {
    onEvent({ type: 'prediction', data: safeJson(e.data) })
  })
  es.addEventListener('alarm', (e) => {
    onEvent({ type: 'alarm', data: safeJson(e.data) })
  })
  es.addEventListener('flow', (e) => {
    onEvent({ type: 'flow', data: safeJson(e.data) })
  })
  es.onerror = () => {
    onEvent({ type: 'error', data: { ok: false } })
  }
  return () => es.close()
}

export async function apiSimulateStart() {
  const res = await fetch(apiUrl('/api/simulate/start'), {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || '启动失败')
  return data
}

export async function apiSimulateStatus() {
  const res = await fetch(apiUrl('/api/simulate/status'), { headers: authHeaders() })
  return await res.json()
}

export async function apiCreateEvent(assetId, type, message, healthLevel, healthScore) {
  const res = await fetch(apiUrl('/api/events'), {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({
      asset_id: assetId,
      type,
      message,
      health_level: healthLevel,
      health_score: healthScore,
    }),
  })
  return await res.json()
}

export async function apiFetchEvents(assetId, limit = 50) {
  const res = await fetch(apiUrl(`/api/events?asset_id=${encodeURIComponent(assetId)}&limit=${limit}`), {
    headers: authHeaders(),
  })
  return await res.json()
}

export async function apiAdminUsers() {
  const res = await fetch(apiUrl('/api/admin/users'), { headers: authHeaders() })
  return await res.json()
}

export async function apiAdminSetUserDevices(userId, devices) {
  const res = await fetch(apiUrl(`/api/admin/users/${userId}/devices`), {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ devices }),
  })
  return await res.json()
}

export async function apiFetchTrends(assetId) {
  const res = await fetch(apiUrl(`/api/trends?asset_id=${encodeURIComponent(assetId)}`), {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error('trends failed')
  return await res.json()
}

export async function fetchFlow() {
  const res = await fetch(apiUrl('/api/flow'), { headers: authHeaders() })
  if (!res.ok) throw new Error('flow failed')
  return await res.json()
}

function safeJson(s) {
  try { return JSON.parse(s) } catch { return s }
}
