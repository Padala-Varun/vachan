import { useEffect, useState } from 'react'
import { AlarmClock, AudioLines, Bot, ChevronDown, Cpu, Database, Moon, Play, Smartphone, Workflow } from 'lucide-react'
import { api, fmtDateTime, timeAgo } from '../api.js'
import { useVachan } from '../store.jsx'
import { STEP_INFO, runSteps } from '../runs.js'
import { Badge, Button, Card, EmptyState, JsonBlock, Spinner } from '../components/ui.jsx'

export const RUN_KIND = {
  conversation: { label: 'Conversation', icon: AudioLines, tone: 'brand' },
  command: { label: 'Voice command', icon: Bot, tone: 'info' },
  reminder: { label: 'Reminder', icon: AlarmClock, tone: 'warning' },
  digest: { label: 'Nightly digest', icon: Moon, tone: 'neutral' },
}

const STEP_KIND = {
  agent: { icon: Bot, label: 'AI agent', tone: 'agent' },
  qdrant: { icon: Database, label: 'Qdrant', tone: 'qdrant' },
  omi: { icon: Smartphone, label: 'Omi', tone: 'omi' },
  local: { icon: Cpu, label: 'On this device', tone: 'neutral' },
}

function engine(step) {
  if (step.kind !== 'agent') return null
  if (step.backend === 'lyzr') return <Badge tone="success">Ran on Lyzr</Badge>
  if (step.backend === 'mock-fallback') return <Badge tone="warning" title="Lyzr call failed; a local agent answered">Lyzr fallback</Badge>
  if (step.backend?.startsWith('local')) return <Badge tone="private">On-device (private)</Badge>
  if (step.backend === 'mock') return <Badge tone="neutral" title="Add this agent's Lyzr ID to backend/.env to run it on Lyzr">Local mode</Badge>
  return null
}

function Step({ step, index, last }) {
  const [open, setOpen] = useState(false)
  const info = STEP_INFO[step.step] || { label: step.step, desc: '' }
  const kind = STEP_KIND[step.kind] || STEP_KIND.local
  const Icon = kind.icon
  const inactive = step.status === 'pending' || step.status === 'skipped'
  return (
    <li className={`step ${step.status} ${last ? 'last' : ''}`}>
      <div className={`step-marker tone-${kind.tone}`}>
        {step.status === 'running' ? <Spinner size={14} /> : <Icon size={15} />}
      </div>
      <div className="step-content">
        <button className="step-head" onClick={() => !inactive && setOpen(!open)} disabled={inactive} aria-expanded={open}>
          <span className="step-index">{index + 1}</span>
          <span className="step-title">
            <strong>{info.label}</strong>
            <span>{info.desc}</span>
          </span>
          <span className="step-meta">
            <Badge tone={kind.tone}>{kind.label}</Badge>
            {engine(step)}
            {step.status === 'error' && <Badge tone="danger">Error</Badge>}
            {step.status === 'pending' && <span className="muted small">Waiting</span>}
            {step.status === 'skipped' && <span className="muted small">Not needed</span>}
            {step.latency != null && <span className="latency">{step.latency} ms</span>}
            {!inactive && <ChevronDown size={16} className={`chev ${open ? 'open' : ''}`} />}
          </span>
        </button>
        {open && (
          <div className="step-io">
            {step.error && <p className="text-danger small">{step.error}</p>}
            <div><h5>Input</h5><JsonBlock value={step.input} /></div>
            <div><h5>Output</h5><JsonBlock value={step.output} /></div>
          </div>
        )}
      </div>
    </li>
  )
}

function RunSummary({ run }) {
  const r = run.result || {}
  const total = run.steps.reduce((s, x) => s + (x.latency || 0), 0)
  const agents = run.steps.filter((s) => s.kind === 'agent').length
  return (
    <div className="run-summary">
      <div><span>Status</span><strong className={run.status === 'ok' ? 'text-success' : run.status === 'error' ? 'text-danger' : ''}>{run.status === 'ok' ? 'Completed' : run.status === 'running' ? 'Running' : run.status}</strong></div>
      <div><span>Agents</span><strong>{agents}</strong></div>
      <div><span>Total time</span><strong>{(total / 1000).toFixed(2)} s</strong></div>
      {run.kind === 'conversation' && (
        <>
          <div><span>New promises</span><strong>{r.created ?? '–'}</strong></div>
          <div><span>Clashes</span><strong className={r.conflicts ? 'text-warning' : ''}>{r.conflicts ?? '–'}</strong></div>
        </>
      )}
      {run.kind === 'command' && r.intent && <div><span>Intent</span><strong>{r.intent}</strong></div>}
    </div>
  )
}

export default function Activity({ selectedRun, onSelectRun, onNavigate }) {
  const { runs, loaded } = useVachan()
  const [follow, setFollow] = useState(true)
  const run = runs.find((r) => r.id === selectedRun) || (follow ? runs[0] : null) || runs[0]

  useEffect(() => {
    if (follow && runs[0] && runs[0].id !== selectedRun) onSelectRun(runs[0].id, true)
  }, [runs[0]?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (loaded && runs.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={Workflow}
          title="No agent runs yet"
          action={<Button variant="primary" icon={Play} onClick={() => api.simulate(['01_pitch_deck.json'])}>Play a demo conversation</Button>}
        >
          When Omi sends a conversation, every step the six agents take appears here, live.
        </EmptyState>
      </Card>
    )
  }
  if (!run) return null
  const kind = RUN_KIND[run.kind] || RUN_KIND.command
  const steps = runSteps(run)

  return (
    <div className="activity">
      <Card title="Runs" description={`${runs.length} recorded`} padded={false} className="runs-card">
        <label className="follow">
          <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> Follow live activity
        </label>
        <ul className="run-list">
          {runs.map((r) => {
            const k = RUN_KIND[r.kind] || RUN_KIND.command
            const Icon = k.icon
            return (
              <li key={r.id}>
                <button className={r.id === run.id ? 'active' : ''} onClick={() => { setFollow(r.id === runs[0].id); onSelectRun(r.id) }}>
                  <span className={`run-icon tone-${k.tone}`}><Icon size={15} /></span>
                  <span className="run-text">
                    <strong>{r.title || k.label}</strong>
                    <span>{k.label} · {timeAgo(r.started)}</span>
                  </span>
                  {r.status === 'running' ? <Spinner size={14} /> : <span className={`status-dot ${r.status === 'ok' ? 'ok' : r.status === 'error' ? 'bad' : 'idle'}`} />}
                </button>
              </li>
            )
          })}
        </ul>
      </Card>

      <Card padded={false} className="run-detail">
        <header className="run-head">
          <span className={`run-icon lg tone-${kind.tone}`}><kind.icon size={18} /></span>
          <div>
            <h2>{run.title || kind.label}</h2>
            <p className="muted small">{kind.label}{run.source ? ` · via ${run.source}` : ''} · {fmtDateTime(run.started)}</p>
          </div>
        </header>
        <RunSummary run={run} />
        <ol className="steps-timeline">
          {steps.map((s, i) => <Step key={s.id} step={s} index={i} last={i === steps.length - 1} />)}
        </ol>
        {run.notes.length > 0 && (
          <div className="run-notes">
            <h5>Sent to phone</h5>
            {run.notes.map((n) => <p key={n.id}>{n.message}</p>)}
          </div>
        )}
        <p className="hint">Click a step to see exactly what the agent received and returned.</p>
      </Card>
    </div>
  )
}
