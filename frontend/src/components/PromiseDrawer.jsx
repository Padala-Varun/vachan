import { useEffect, useState } from 'react'
import { AlertTriangle, BellRing, CalendarClock, Check, Lock, MessageSquareQuote, RotateCcw, Trash2 } from 'lucide-react'
import { api, fmtDateTime, fmtDue, hasConflict, toLocalInput } from '../api.js'
import { useVachan } from '../store.jsx'
import { Direction, StatusBadge } from './PromiseRow.jsx'
import { Avatar, Badge, Button, ConfirmDialog, Drawer, RedactedText, Switch } from './ui.jsx'

export default function PromiseDrawer({ promise, onClose }) {
  const { commitments, refresh, toast } = useVachan()
  const c = promise && (commitments.find((x) => x.id === promise.id) || promise)
  const [due, setDue] = useState('')
  const [transcript, setTranscript] = useState([])
  const [confirm, setConfirm] = useState(false)

  useEffect(() => {
    if (!c) return
    setDue(toLocalInput(c.due_at))
    setTranscript([])
    if (c.source_conversation_id) api.conversation(c.source_conversation_id).then(setTranscript).catch(() => {})
  }, [c?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!c) return null
  const clashes = (c.conflict_with || []).map((id) => commitments.find((x) => x.id === id)).filter(Boolean)

  const run = (fn, success) => async () => {
    try {
      await fn()
      if (success) toast(success, 'success')
      refresh()
    } catch (e) {
      toast(e.message, 'danger', 'Something went wrong')
    }
  }

  const footer = (
    <>
      <Button variant="ghost-danger" icon={Trash2} onClick={() => setConfirm(true)}>Delete</Button>
      <div className="spacer" />
      {c.status === 'open' && c.owner === 'me' && (
        <Button icon={BellRing} onClick={run(() => api.remindNow(c.id), 'Reminder sent.')}>Remind me now</Button>
      )}
      {c.status === 'open' ? (
        <Button variant="primary" icon={Check} disabled={c.owner !== 'me'} onClick={run(() => api.patchCommitment(c.id, { status: 'done' }), 'Marked as kept.')}>Mark as kept</Button>
      ) : (
        <Button icon={RotateCcw} onClick={run(() => api.patchCommitment(c.id, { status: 'open' }), 'Reopened.')}>Reopen</Button>
      )}
    </>
  )

  return (
    <>
      <Drawer open={!!c} onClose={onClose} title="Promise details" width={520} footer={footer}>
        <div className="detail-hero">
          <Avatar name={c.counterparty} size={44} />
          <div>
            <h3><RedactedText text={c.action} /></h3>
            <Direction c={c} />
          </div>
        </div>

        {hasConflict(c) && (
          <div className="callout warning">
            <AlertTriangle size={18} />
            <div>
              <strong>Schedule clash</strong>
              {clashes.length === 0 ? <p>{c.conflict_reason}</p> : (
                <>
                  <p>This overlaps with:</p>
                  <ul className="clash-list">
                    {clashes.map((x) => <li key={x.id}><RedactedText text={x.action} /> <span className="muted">· {x.counterparty}, {fmtDue(x.due_at)}</span></li>)}
                  </ul>
                </>
              )}
            </div>
          </div>
        )}

        <dl className="facts">
          <div><dt>Status</dt><dd><StatusBadge c={c} /></dd></div>
          <div><dt>Deadline</dt><dd>{fmtDue(c.due_at)}</dd></div>
          <div><dt>Confidence</dt><dd>{c.confidence != null ? `${Math.round(c.confidence * 100)}%` : '–'}</dd></div>
          <div><dt>Captured</dt><dd>{c.created_at ? fmtDateTime(c.created_at) : '–'}</dd></div>
        </dl>

        {c.status === 'open' && (
          <section className="detail-section">
            <h4><CalendarClock size={15} /> Change deadline</h4>
            <div className="inline-form">
              <input type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} />
              <Button onClick={run(() => api.patchCommitment(c.id, { due_at: new Date(due).toISOString() }), 'Deadline updated, reminders rescheduled.')}>Save</Button>
            </div>
          </section>
        )}

        <section className="detail-section">
          <h4><Lock size={15} /> Privacy</h4>
          <Switch
            checked={c.visibility === 'private'}
            onChange={(v) => run(() => api.patchCommitment(c.id, { visibility: v ? 'private' : 'shared' }), v ? 'Now private. AI agents will not see it.' : 'Shared with your agents again.')()}
            label={c.visibility === 'private' ? 'Private: never sent to any AI agent' : 'Shared: agents can use it for recall and conflict checks'}
          />
        </section>

        {c.quote && (
          <section className="detail-section">
            <h4><MessageSquareQuote size={15} /> What was said</h4>
            <blockquote className="quote">“<RedactedText text={c.quote} />”</blockquote>
          </section>
        )}

        {transcript.length > 0 && (
          <section className="detail-section">
            <h4>Source conversation <Badge tone="neutral">redacted</Badge></h4>
            <div className="transcript">
              {transcript.map((m) => <pre key={m.id}><RedactedText text={m.text} /></pre>)}
            </div>
          </section>
        )}

        {c.history?.length > 0 && (
          <section className="detail-section">
            <h4>History</h4>
            <ol className="history">
              {c.history.map((h, i) => (
                <li key={i}><span>{h.event}</span><time className="muted small">{fmtDateTime(h.at)}</time></li>
              ))}
            </ol>
          </section>
        )}
      </Drawer>
      <ConfirmDialog
        open={confirm}
        onClose={() => setConfirm(false)}
        title="Delete this promise?"
        message="It will be permanently removed from Qdrant and its reminders cancelled. This is logged in your audit trail."
        confirmLabel="Delete promise"
        onConfirm={async () => { await api.deleteCommitment(c.id); toast('Promise deleted.', 'neutral'); onClose(); refresh() }}
      />
    </>
  )
}
