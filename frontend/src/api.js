// Empty when the dashboard is served by the backend itself (local / same origin);
// set VITE_API_BASE (e.g. the Modal URL) when the dashboard is hosted separately.
export const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '')

async function call(path, options = {}) {
  const res = await fetch(API_BASE + path, {
    headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  })
  if (!res.ok) {
    let detail = await res.text()
    try { detail = JSON.parse(detail).detail || detail } catch { /* plain text */ }
    throw new Error(detail || `Request failed (${res.status})`)
  }
  return res.json()
}

export const api = {
  health: () => call('/api/health'),
  commitments: () => call('/api/commitments'),
  patchCommitment: (id, body) => call(`/api/commitments/${id}`, { method: 'PATCH', body }),
  deleteCommitment: (id) => call(`/api/commitments/${id}`, { method: 'DELETE' }),
  memories: (q) => call(`/api/memories${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  conversation: (id) => call(`/api/memories?conversation_id=${encodeURIComponent(id)}`),
  patchMemory: (id, body) => call(`/api/memories/${id}`, { method: 'PATCH', body }),
  deleteMemory: (id) => call(`/api/memories/${id}`, { method: 'DELETE' }),
  ask: (text, source = 'dashboard') => call('/api/ask', { method: 'POST', body: { text, source } }),
  notifications: () => call('/api/notifications'),
  audit: () => call('/api/audit'),
  traces: () => call('/api/traces'),
  fixtures: () => call('/api/demo/fixtures'),
  simulate: (fixtures) => call('/api/demo/simulate', { method: 'POST', body: { fixtures } }),
  remindNow: (id) => call(`/api/demo/remind/${id}`, { method: 'POST' }),
  digest: () => call('/api/demo/digest', { method: 'POST' }),
  reset: () => call('/api/demo/reset', { method: 'POST' }),
}

const dayDiff = (d) => {
  const now = new Date()
  const a = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const b = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  return Math.round((a - b) / 86400000)
}

export function fmtDay(iso) {
  if (!iso) return 'No deadline'
  const d = new Date(iso)
  const diff = dayDiff(d)
  if (diff === 0) return 'Today'
  if (diff === 1) return 'Tomorrow'
  if (diff === -1) return 'Yesterday'
  if (diff > 1 && diff < 7) return d.toLocaleDateString([], { weekday: 'long' })
  return d.toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' })
}

export const fmtTime = (iso) => new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })

export function fmtDue(iso) {
  if (!iso) return 'No deadline'
  return `${fmtDay(iso)}, ${fmtTime(iso)}`
}

export function fmtDateTime(iso) {
  return new Date(iso).toLocaleString([], { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })
}

export function timeAgo(iso) {
  if (!iso) return ''
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 45) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return `${Math.round(s / 86400)} d ago`
}

export function toLocalInput(iso) {
  const d = iso ? new Date(iso) : new Date(Date.now() + 86400000)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export const stripEmoji = (s = '') => s.replace(/^\p{Extended_Pictographic}️?\s*/u, '')

export const isMine = (c) => c.owner === 'me'
export const isOpen = (c) => c.status === 'open'
export const hasConflict = (c) => isOpen(c) && !!c.conflict_reason
