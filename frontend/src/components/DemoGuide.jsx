import { useState } from 'react'
import { AlertTriangle, AudioLines, Check, CheckCircle2, Mic, Play, ShieldCheck, X } from 'lucide-react'
import { api } from '../api.js'
import { useVachan } from '../store.jsx'
import { Button } from './ui.jsx'

const STORE_KEY = 'vachan-guide-done'

const STEPS = [
  {
    id: 'conversation', icon: AudioLines, title: 'Play a conversation',
    desc: 'You promise Rahul a pitch deck by Thursday. Watch 6 Lyzr agents pick out every promise.',
    cta: 'Play', kind: 'play', fixture: '01_pitch_deck.json', goto: 'activity',
  },
  {
    id: 'clash', icon: AlertTriangle, title: 'Create a clash',
    desc: 'In a standup you promise Priya the same Thursday 6 PM slot. Vachan warns you.',
    cta: 'Play', kind: 'play', fixture: '02_conflict.json', goto: 'activity',
  },
  {
    id: 'ask', icon: Mic, title: 'Ask out loud',
    desc: '“What do I owe Rahul this week?” Speak with the mic, or click to ask.',
    cta: 'Ask', kind: 'ask', text: 'What do I owe Rahul this week?', needs: 'conversation',
  },
  {
    id: 'keep', icon: CheckCircle2, title: 'Keep a promise',
    desc: 'Tell Vachan “I sent the pitch deck to Rahul” and the promise is marked kept.',
    cta: 'Say it', kind: 'ask', text: 'I sent the pitch deck to Rahul', needs: 'conversation',
  },
  {
    id: 'privacy', icon: ShieldCheck, title: 'Test privacy',
    desc: 'A call about a loan and a parent’s health: amounts and health details are masked, the memory goes private.',
    cta: 'Play', kind: 'play', fixture: '03_sensitive.json', goto: 'memory',
  },
]

function loadDone() {
  try { return new Set(JSON.parse(localStorage.getItem(STORE_KEY) || '[]')) } catch { return new Set() }
}
function saveDone(done) {
  try { localStorage.setItem(STORE_KEY, JSON.stringify([...done])) } catch { /* storage unavailable */ }
}

/** A one-click tour of everything Vachan does, for first-time visitors and judges. */
export default function DemoGuide({ onNavigate, onAsk, onHide }) {
  const { toast } = useVachan()
  const [done, setDone] = useState(loadDone)
  const [busy, setBusy] = useState(null)

  const mark = (id) => setDone((prev) => {
    const next = new Set(prev).add(id)
    saveDone(next)
    return next
  })

  async function run(step) {
    if (step.kind === 'ask') {
      mark(step.id)
      onAsk(step.text)
      return
    }
    setBusy(step.id)
    try {
      await api.simulate([step.fixture])
      mark(step.id)
      toast('Omi just sent this conversation to Vachan. Watch each agent step complete.', 'info', step.title)
      onNavigate(step.goto)
    } catch (e) {
      toast(e.message, 'danger', 'Could not start')
    } finally {
      setBusy(null)
    }
  }

  const count = STEPS.filter((s) => done.has(s.id)).length

  return (
    <section className="guide" aria-label="Try Vachan">
      <header className="guide-head">
        <div>
          <h2>Try Vachan in 60 seconds</h2>
          <p>Each step does the real thing: live Lyzr agents, Qdrant memory, and a notification on the phone.</p>
        </div>
        <div className="guide-progress">
          <span>{count} of {STEPS.length} done</span>
          <div className="guide-bar"><span style={{ width: `${(count / STEPS.length) * 100}%` }} /></div>
        </div>
        {onHide && <button className="guide-close" onClick={onHide} aria-label="Hide guide" title="Hide guide"><X size={16} /></button>}
      </header>
      <ol className="guide-steps">
        {STEPS.map((s, i) => {
          const Icon = s.icon
          const isDone = done.has(s.id)
          const locked = s.needs && !done.has(s.needs)
          return (
            <li key={s.id} className={`guide-step ${isDone ? 'done' : ''}`}>
              <div className="guide-step-top">
                <span className="guide-num">{isDone ? <Check size={14} strokeWidth={3} /> : i + 1}</span>
                <Icon size={18} className="guide-icon" />
              </div>
              <strong>{s.title}</strong>
              <p>{s.desc}</p>
              <Button
                size="sm"
                variant={isDone ? 'secondary' : 'primary'}
                icon={s.kind === 'ask' ? Mic : Play}
                disabled={busy === s.id || locked}
                title={locked ? 'Do step 1 first' : undefined}
                onClick={() => run(s)}
              >
                {busy === s.id ? 'Starting…' : locked ? 'Do step 1 first' : isDone ? 'Again' : s.cta}
              </Button>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
