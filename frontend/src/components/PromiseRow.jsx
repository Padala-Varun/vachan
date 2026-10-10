import { useState } from 'react'
import { AlertTriangle, Check, ChevronRight, Lock } from 'lucide-react'
import { api, fmtDue, hasConflict } from '../api.js'
import { useVachan } from '../store.jsx'
import { Avatar, Badge, RedactedText } from './ui.jsx'

export function DueBadge({ c }) {
  if (c.status === 'done') return <Badge tone="success">Kept</Badge>
  if (!c.due_at) return <Badge tone="neutral">No deadline</Badge>
  const tone = c.urgency === 'overdue' ? 'danger' : c.urgency === 'soon' ? 'warning' : 'neutral'
  return <Badge tone={tone}>{c.urgency === 'overdue' ? 'Overdue · ' : ''}{fmtDue(c.due_at)}</Badge>
}

export function StatusBadge({ c }) {
  if (c.status === 'done') return <Badge tone="success">Kept</Badge>
  if (c.urgency === 'overdue') return <Badge tone="danger">Overdue</Badge>
  if (c.urgency === 'soon') return <Badge tone="warning">Due soon</Badge>
  return <Badge tone="info">Open</Badge>
}

export function Direction({ c }) {
  return c.owner === 'me'
    ? <span className="direction">You promised <b>{c.counterparty || 'someone'}</b></span>
    : <span className="direction"><b>{c.counterparty || 'Someone'}</b> promised you</span>
}

export default function PromiseRow({ c, onOpen, compact = false }) {
  const { refresh, toast } = useVachan()
  const [busy, setBusy] = useState(false)
  const done = c.status === 'done'

  async function toggleDone(e) {
    e.stopPropagation()
    setBusy(true)
    try {
      await api.patchCommitment(c.id, { status: done ? 'open' : 'done' })
      toast(done ? 'Moved back to open promises.' : `Nice, you kept your word: ${c.action}`, done ? 'neutral' : 'success')
      refresh()
    } catch (err) {
      toast(err.message, 'danger', 'Could not update')
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className={`promise-row ${done ? 'done' : ''} ${hasConflict(c) ? 'conflict' : ''} ${compact ? 'compact' : ''}`}>
      <button
        className={`check ${done ? 'checked' : ''}`}
        onClick={toggleDone}
        disabled={busy || c.owner !== 'me'}
        aria-label={done ? 'Mark as open' : 'Mark as kept'}
        title={c.owner !== 'me' ? 'Promised to you, so the other person marks it' : done ? 'Mark as open' : 'Mark as kept'}
      >
        {done && <Check size={13} strokeWidth={3} />}
      </button>
      <button className="promise-main" onClick={() => onOpen(c)}>
        <Avatar name={c.counterparty} size={compact ? 28 : 34} />
        <span className="promise-text">
          <span className="promise-action"><RedactedText text={c.action} /></span>
          <span className="promise-sub">
            <Direction c={c} />
            {hasConflict(c) && <span className="inline-warn"><AlertTriangle size={13} /> Schedule clash</span>}
          </span>
        </span>
        <span className="promise-side">
          {c.visibility === 'private' && <Badge tone="private" icon={Lock} title="Private: never sent to AI agents">Private</Badge>}
          <DueBadge c={c} />
          <ChevronRight size={16} className="chev" />
        </span>
      </button>
    </li>
  )
}
