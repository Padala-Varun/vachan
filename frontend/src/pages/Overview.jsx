import { useState } from 'react'
import { AlertTriangle, ArrowRight, CalendarDays, CheckCircle2, Clock, Handshake, Inbox, Mic, Play, Plug, Sparkles, Workflow } from 'lucide-react'
import { api, fmtDay, hasConflict, isMine, isOpen, timeAgo } from '../api.js'
import { useVachan } from '../store.jsx'
import PromiseRow from '../components/PromiseRow.jsx'
import { Badge, Button, Card, EmptyState, Spinner } from '../components/ui.jsx'
import { RUN_KIND } from './Activity.jsx'

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
}

function Stat({ icon: Icon, label, value, hint, tone = 'neutral' }) {
  return (
    <div className={`stat stat-${tone}`}>
      <div className="stat-icon"><Icon size={18} /></div>
      <div>
        <div className="stat-value">{value}</div>
        <div className="stat-label">{label}</div>
        {hint && <div className="stat-hint">{hint}</div>}
      </div>
    </div>
  )
}

function ScoreRing({ kept, total }) {
  const pct = total ? Math.round((kept / total) * 100) : 0
  const r = 34
  const circ = 2 * Math.PI * r
  return (
    <div className="score-ring">
      <svg viewBox="0 0 80 80" width="88" height="88" aria-hidden="true">
        <circle cx="40" cy="40" r={r} className="ring-track" />
        <circle cx="40" cy="40" r={r} className="ring-value" strokeDasharray={circ} strokeDashoffset={circ * (1 - pct / 100)} />
      </svg>
      <div className="score-label"><strong>{pct}%</strong><span>kept</span></div>
    </div>
  )
}

export function Onboarding({ onNavigate, compact = false }) {
  const { toast } = useVachan()
  const [busy, setBusy] = useState(false)
  async function loadDemo() {
    setBusy(true)
    try {
      const res = await api.simulate()
      toast(`Playing ${res.conversations.length} demo conversations. Watch the agents work.`, 'info', 'Demo started')
      onNavigate('activity')
    } catch (e) {
      toast(e.message, 'danger', 'Could not start demo')
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className={`welcome ${compact ? 'compact' : ''}`}>
      <div className="welcome-text">
        <Badge tone="brand" icon={Sparkles}>Welcome to Vachan</Badge>
        <h2>Never forget a promise again.</h2>
        <p>
          Vachan listens to your conversations through Omi, catches every commitment you make or receive, warns you
          about clashes and reminds you before deadlines.
        </p>
        <div className="welcome-actions">
          <Button variant="primary" icon={Play} onClick={loadDemo} disabled={busy}>{busy ? 'Starting…' : 'Try it with demo conversations'}</Button>
          <Button icon={Plug} onClick={() => onNavigate('connections')}>Connect Omi</Button>
        </div>
      </div>
      <ol className="steps">
        <li><span className="step-icon"><Mic size={16} /></span><div><strong>Talk normally</strong><p>“I'll send you the deck by Thursday.”</p></div></li>
        <li><span className="step-icon"><Workflow size={16} /></span><div><strong>Agents take notes</strong><p>Six Lyzr agents extract, de-duplicate and check for clashes.</p></div></li>
        <li><span className="step-icon"><Handshake size={16} /></span><div><strong>Keep your word</strong><p>Get nudged on your phone, or ask “Hey Vachan, what do I owe Rahul?”</p></div></li>
      </ol>
    </section>
  )
}

export default function Overview({ onNavigate, onOpenPromise, onOpenRun }) {
  const { commitments, runs, loaded } = useVachan()
  const mine = commitments.filter(isMine)
  const openMine = mine.filter(isOpen)
  const owedToMe = commitments.filter((c) => !isMine(c) && isOpen(c))
  const dueSoon = openMine.filter((c) => c.urgency === 'soon' || c.urgency === 'overdue')
  const attention = commitments.filter((c) => isOpen(c) && (hasConflict(c) || c.urgency === 'overdue'))
  const kept = mine.filter((c) => c.status === 'done').length

  const upcoming = commitments.filter((c) => isOpen(c) && c.due_at && c.urgency !== 'overdue').slice(0, 8)
  const byDay = upcoming.reduce((acc, c) => {
    const day = fmtDay(c.due_at)
    ;(acc[day] = acc[day] || []).push(c)
    return acc
  }, {})

  if (!loaded) return <div className="center-pad"><Spinner size={24} /></div>
  if (commitments.length === 0) return <Onboarding onNavigate={onNavigate} />

  return (
    <div className="stack">
      <div className="hello">
        <div>
          <h2>{greeting()}.</h2>
          <p className="muted">
            {openMine.length
              ? `You have ${openMine.length} open promise${openMine.length > 1 ? 's' : ''}${dueSoon.length ? `, ${dueSoon.length} due within a day` : ''}.`
              : 'You are all caught up.'}
          </p>
        </div>
        <ScoreRing kept={kept} total={mine.length} />
      </div>

      <div className="stats">
        <Stat icon={Handshake} label="I owe" value={openMine.length} hint="Open promises you made" tone="brand" />
        <Stat icon={Inbox} label="Owed to me" value={owedToMe.length} hint="Promises others made you" tone="info" />
        <Stat icon={Clock} label="Due in 24 hours" value={dueSoon.length} hint="Including overdue" tone={dueSoon.length ? 'warning' : 'neutral'} />
        <Stat icon={AlertTriangle} label="Schedule clashes" value={commitments.filter(hasConflict).length} hint="Detected by the Curator" tone={commitments.some(hasConflict) ? 'danger' : 'neutral'} />
      </div>

      <div className="two-col">
        <div className="stack">
          <Card
            title="Needs your attention"
            description="Clashes and overdue promises."
            actions={<Button size="sm" variant="ghost" onClick={() => onNavigate('promises')}>View all <ArrowRight size={14} /></Button>}
            padded={false}
          >
            {attention.length === 0 ? (
              <EmptyState icon={CheckCircle2} title="Nothing needs attention">No clashes or overdue promises right now.</EmptyState>
            ) : (
              <ul className="promise-list">{attention.map((c) => <PromiseRow key={c.id} c={c} onOpen={onOpenPromise} />)}</ul>
            )}
          </Card>

          <Card title="Coming up" description="Your next deadlines, by day." padded={false}>
            {upcoming.length === 0 ? (
              <EmptyState icon={CalendarDays} title="No upcoming deadlines" />
            ) : (
              Object.entries(byDay).map(([day, items]) => (
                <div key={day} className="day-group">
                  <h4 className="day-label">{day}</h4>
                  <ul className="promise-list">{items.map((c) => <PromiseRow key={c.id} c={c} onOpen={onOpenPromise} compact />)}</ul>
                </div>
              ))
            )}
          </Card>
        </div>

        <Card
          title="Recent agent activity"
          description="Live trace of every pipeline run."
          actions={<Button size="sm" variant="ghost" onClick={() => onNavigate('activity')}>Open <ArrowRight size={14} /></Button>}
          padded={false}
        >
          {runs.length === 0 ? (
            <EmptyState icon={Workflow} title="No activity yet" />
          ) : (
            <ul className="activity-list">
              {runs.slice(0, 8).map((r) => {
                const k = RUN_KIND[r.kind] || RUN_KIND.command
                const Icon = k.icon
                return (
                  <li key={r.id}>
                    <button onClick={() => onOpenRun(r.id)}>
                      <span className={`run-icon tone-${k.tone}`}><Icon size={15} /></span>
                      <span className="activity-text">
                        <strong>{r.title || k.label}</strong>
                        <span className="muted small">{k.label} · {r.steps.length} steps · {timeAgo(r.started)}</span>
                      </span>
                      <span className={`status-dot ${r.status === 'ok' ? 'ok' : r.status === 'error' ? 'bad' : 'run'}`} />
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}
