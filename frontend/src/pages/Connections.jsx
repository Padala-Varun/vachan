import { useEffect, useState } from 'react'
import { Bot, Check, Copy, Database, Moon, Play, RotateCcw, Smartphone } from 'lucide-react'
import { API_BASE, api } from '../api.js'
import { useVachan } from '../store.jsx'
import { Badge, Button, Card, ConfirmDialog } from '../components/ui.jsx'

const AGENTS = {
  privacy_guard: 'Privacy Guard',
  extractor: 'Promise Extractor',
  curator: 'Curator & Conflict Detector',
  nudger: 'Nudger',
  router: 'Router',
  recall: 'Recall',
}

function CopyField({ label, value }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="copy-field">
      <span className="copy-label">{label}</span>
      <code>{value}</code>
      <button
        onClick={() => { navigator.clipboard?.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 1500) }}
        aria-label={`Copy ${label}`}
      >
        {copied ? <Check size={14} /> : <Copy size={14} />}
      </button>
    </div>
  )
}

function Service({ icon: Icon, name, tone, ok, status, children }) {
  return (
    <Card className="service-card">
      <div className="service-top">
        <span className={`service-logo tone-${tone}`}><Icon size={20} /></span>
        <div>
          <h3>{name}</h3>
          <Badge tone={ok ? 'success' : 'warning'}>{status}</Badge>
        </div>
      </div>
      {children}
    </Card>
  )
}

export default function Connections({ onNavigate }) {
  const { health, refresh, toast, clearEvents } = useVachan()
  const [fixtures, setFixtures] = useState([])
  const [confirmReset, setConfirmReset] = useState(false)
  useEffect(() => { api.fixtures().then(setFixtures).catch(() => {}) }, [])

  if (!health) return null
  const agents = Object.entries(health.agents)
  const live = agents.filter(([, m]) => m === 'lyzr').length
  const origin = API_BASE || window.location.origin.replace(':5173', ':8000')
  const isPublic = !/localhost|127\.0\.0\.1/.test(origin)

  async function play(names) {
    try {
      await api.simulate(names)
      toast('Demo conversation sent. The agents are processing it now.', 'info', 'Simulating Omi')
      onNavigate('activity')
    } catch (e) {
      toast(e.message, 'danger')
    }
  }

  return (
    <div className="stack">
      <div className="services">
        <Service icon={Smartphone} name="Omi" tone="omi" ok={health.omi === 'omi'} status={health.omi === 'omi' ? 'Connected' : 'Simulator mode'}>
          <p className="muted">Captures your conversations and delivers nudges to your phone.</p>
          <p className="field-title">
            {isPublic ? 'Webhook URLs: paste these into your Omi app' : 'Webhook URLs (use your public tunnel address in place of localhost)'}
          </p>
          <CopyField label="Conversation created" value={`${origin}/omi/conversation`} />
          <CopyField label="Real-time transcript" value={`${origin}/omi/realtime`} />
          {health.omi !== 'omi' && <p className="setup-note">Add <code>OMI_APP_ID</code> and <code>OMI_APP_SECRET</code> to <code>backend/.env</code>, then restart. See docs/OMI_SETUP.md.</p>}
          <p className="field-title">Wake phrases</p>
          <div className="chips">{health.wake_phrases.map((w) => <Badge key={w} tone="neutral">“{w}”</Badge>)}</div>
        </Service>

        <Service icon={Bot} name="Lyzr" tone="agent" ok={live > 0} status={`${live} of ${agents.length} agents live`}>
          <p className="muted">Six agents run the reasoning. Agents without an ID use a built-in local version.</p>
          <ul className="agent-list">
            {agents.map(([key, mode]) => {
              const error = health.agent_errors?.[key]
              return (
                <li key={key} className={error ? 'has-error' : ''}>
                  <div className="agent-row">
                    <span>{AGENTS[key] || key}</span>
                    {error
                      ? <Badge tone="danger">Needs fixing</Badge>
                      : <Badge tone={mode === 'lyzr' ? 'success' : 'neutral'}>{mode === 'lyzr' ? 'Lyzr' : 'Local'}</Badge>}
                  </div>
                  {error && <p className="agent-error">{error}</p>}
                </li>
              )
            })}
          </ul>
          {live < agents.length && <p className="setup-note">Create the agents in Lyzr Studio and paste their IDs into <code>backend/.env</code>. See docs/LYZR_SETUP.md.</p>}
        </Service>

        <Service icon={Database} name="Qdrant" tone="qdrant" ok status={health.qdrant === 'cloud' ? 'Cloud cluster' : 'Local storage'}>
          <p className="muted">Long-term vector memory shared by all agents.</p>
          <dl className="facts compact">
            <div><dt>Conversation chunks</dt><dd>{health.stats.transcripts}</dd></div>
            <div><dt>Promises</dt><dd>{health.stats.commitments}</dd></div>
            <div><dt>Embeddings</dt><dd>{health.embedder === 'FastEmbedder' ? 'bge-small (on-device)' : 'Hash (test mode)'}</dd></div>
            <div><dt>Scheduled reminders</dt><dd>{health.scheduled_jobs}</dd></div>
          </dl>
          {health.qdrant !== 'cloud' && <p className="setup-note">To use Qdrant Cloud, add <code>QDRANT_URL</code> and <code>QDRANT_API_KEY</code> to <code>backend/.env</code>.</p>}
        </Service>
      </div>

      <Card title="Demo tools" description="Replay realistic conversations exactly as Omi would send them. No device needed.">
        <ul className="fixture-list">
          {fixtures.map((f) => (
            <li key={f.name}>
              <div><strong>{f.title}</strong><span className="muted small">{f.segments} lines of dialogue</span></div>
              <Button size="sm" icon={Play} onClick={() => play([f.name])}>Play</Button>
            </li>
          ))}
        </ul>
        <div className="button-row">
          <Button variant="primary" icon={Play} onClick={() => play()}>Play all conversations</Button>
          <Button icon={Moon} onClick={async () => { await api.digest(); toast('Nightly digest sent.', 'success'); refresh() }}>Send nightly digest now</Button>
          <div className="spacer" />
          <Button variant="ghost-danger" icon={RotateCcw} onClick={() => setConfirmReset(true)}>Reset all data</Button>
        </div>
      </Card>

      <ConfirmDialog
        open={confirmReset}
        onClose={() => setConfirmReset(false)}
        title="Reset all data?"
        message="This deletes every promise, memory, trace and notification. Use it to start a clean demo."
        confirmLabel="Reset everything"
        onConfirm={async () => { await api.reset(); clearEvents(); toast('All data cleared.', 'neutral'); refresh() }}
      />
    </div>
  )
}
