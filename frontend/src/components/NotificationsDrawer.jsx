import { AlertTriangle, BellOff, CalendarClock, CheckCircle2, Handshake, Moon, PlusCircle, Search, Trash2 } from 'lucide-react'
import { timeAgo } from '../api.js'
import { useVachan } from '../store.jsx'
import { Badge, Drawer, EmptyState } from './ui.jsx'

const KIND = {
  conflict: { icon: AlertTriangle, tone: 'warning', label: 'Conflict' },
  captured: { icon: Handshake, tone: 'info', label: 'Captured' },
  reminder: { icon: CalendarClock, tone: 'info', label: 'Reminder' },
  digest: { icon: Moon, tone: 'neutral', label: 'Digest' },
  recall: { icon: Search, tone: 'neutral', label: 'Answer' },
  mark_done: { icon: CheckCircle2, tone: 'success', label: 'Kept' },
  forget: { icon: Trash2, tone: 'danger', label: 'Forgotten' },
  add: { icon: PlusCircle, tone: 'info', label: 'Added' },
}

const stripEmoji = (s) => s.replace(/^\p{Extended_Pictographic}️?\s*/u, '')

export default function NotificationsDrawer({ open, onClose }) {
  const { notifications, health } = useVachan()
  const live = health?.omi === 'omi'
  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="Notifications"
      subtitle={live ? 'Also delivered to your phone through Omi.' : 'Simulator mode: connect Omi to receive these on your phone.'}
      width={420}
    >
      {notifications.length === 0 ? (
        <EmptyState icon={BellOff} title="No notifications yet">
          Vachan nudges you when it captures a promise, finds a clash, or a deadline is close.
        </EmptyState>
      ) : (
        <ul className="notif-list">
          {notifications.map((n) => {
            const k = KIND[n.kind] || KIND.captured
            const Icon = k.icon
            return (
              <li key={n.id} className={`notif ${n.priority === 'high' ? 'high' : ''}`}>
                <span className={`notif-icon tone-${k.tone}`}><Icon size={16} /></span>
                <div className="notif-body">
                  <div className="notif-meta">
                    <Badge tone={k.tone}>{k.label}</Badge>
                    <span className="muted small">{timeAgo(n.at)}</span>
                  </div>
                  <p>{stripEmoji(n.message)}</p>
                  {n.channel === 'omi' && (
                    <span className={`small ${n.delivered ? 'text-success' : n.error?.startsWith('Phone limit') ? 'text-warning' : 'text-danger'}`}>
                      {n.delivered ? 'Delivered to phone' : n.error?.startsWith('Phone limit') ? n.error : `Not delivered: ${n.error}`}
                    </span>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </Drawer>
  )
}
