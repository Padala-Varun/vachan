import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { API_BASE, api, stripEmoji } from './api.js'
import { buildRuns } from './runs.js'

const VachanContext = createContext(null)
export const useVachan = () => useContext(VachanContext)

let toastSeq = 0

export function VachanProvider({ children }) {
  const [health, setHealth] = useState(null)
  const [commitments, setCommitments] = useState([])
  const [notifications, setNotifications] = useState([])
  const [events, setEvents] = useState([])
  const [online, setOnline] = useState(null) // null = connecting
  const [loaded, setLoaded] = useState(false)
  const [toasts, setToasts] = useState([])
  const [version, setVersion] = useState(0)
  const [seenAt, setSeenAt] = useState(() => new Date().toISOString())
  const timer = useRef(null)

  const toast = useCallback((message, tone = 'neutral', title) => {
    const id = ++toastSeq
    setToasts((t) => [...t.slice(-3), { id, message, tone, title }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000)
  }, [])
  const dismissToast = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), [])

  const refresh = useCallback(async () => {
    try {
      const [h, c, n] = await Promise.all([api.health(), api.commitments(), api.notifications()])
      setHealth(h); setCommitments(c); setNotifications(n)
      setVersion((v) => v + 1)
    } catch (e) {
      console.warn('refresh failed', e)
    } finally {
      setLoaded(true)
    }
  }, [])

  const scheduleRefresh = useCallback(() => {
    clearTimeout(timer.current)
    timer.current = setTimeout(refresh, 250)
  }, [refresh])

  useEffect(() => {
    refresh()
    const es = new EventSource(`${API_BASE}/api/stream`)
    // (re)load history on every (re)connect so nothing is missed while disconnected
    es.onopen = () => {
      setOnline(true)
      api.traces().then(setEvents).catch(() => {})
      refresh()
    }
    es.onerror = () => setOnline(false)
    es.onmessage = (msg) => {
      const ev = JSON.parse(msg.data)
      setEvents((prev) => [...prev.slice(-1500), ev])
      if (ev.type === 'notification') {
        const tone = ev.priority === 'high' ? 'warning' : ev.kind === 'mark_done' ? 'success' : 'info'
        toast(stripEmoji(ev.message), tone, ev.priority === 'high' ? 'Heads up' : 'Vachan')
      }
      if (['run_end', 'notification'].includes(ev.type)) scheduleRefresh()
    }
    return () => es.close()
  }, [refresh, scheduleRefresh, toast])

  const runs = useMemo(() => buildRuns(events), [events])
  const unread = notifications.filter((n) => new Date(n.at) > new Date(seenAt)).length

  const value = {
    health, commitments, notifications, runs, online, loaded, version, unread,
    refresh, toast, toasts, dismissToast,
    markNotificationsSeen: () => setSeenAt(new Date().toISOString()),
    clearEvents: () => setEvents([]),
  }
  return <VachanContext.Provider value={value}>{children}</VachanContext.Provider>
}
