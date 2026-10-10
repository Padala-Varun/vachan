import { useEffect, useState } from 'react'
import { Cpu, EyeOff, FileClock, HardDrive, Lock, MicOff, ScanFace, Trash2 } from 'lucide-react'
import { api, fmtDateTime } from '../api.js'
import { useVachan } from '../store.jsx'
import { Badge, Button, Card, EmptyState } from '../components/ui.jsx'

const PROTECTIONS = [
  { icon: MicOff, title: 'Off the record', text: 'Say “off the record” and nothing is stored until you say “back on the record”.' },
  { icon: ScanFace, title: 'Personal data masking', text: 'Phone numbers, emails, Aadhaar, PAN, cards and OTPs are masked on this machine before anything leaves it.' },
  { icon: EyeOff, title: 'Privacy Guard agent', text: 'Redacts health and money details and marks sensitive parts of a conversation as private.' },
  { icon: Lock, title: 'Private memories', text: 'Private items are never included in any prompt sent to an AI agent. Their reminders are written on-device.' },
  { icon: Cpu, title: 'Local embeddings', text: 'Text is turned into vectors on this machine, so raw conversations never go to an embedding service.' },
  { icon: HardDrive, title: 'Your storage', text: 'Qdrant can run fully on your own disk, or on your own Qdrant Cloud cluster.' },
]

const ACTION = {
  delete: { tone: 'danger', label: 'Deleted' },
  visibility: { tone: 'info', label: 'Visibility' },
}

export default function Privacy() {
  const { version, refresh, toast } = useVachan()
  const [audit, setAudit] = useState([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)

  useEffect(() => { api.audit().then(setAudit).catch(() => {}) }, [version])

  async function forget(e) {
    e.preventDefault()
    if (!text.trim()) return
    setBusy(true)
    try {
      const res = await api.ask(`forget ${text.trim()}`)
      setResult(res.answer)
      setText('')
      toast(res.answer, 'neutral', 'Forget request done')
      refresh()
    } catch (err) {
      toast(err.message, 'danger')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack">
      <Card title="Right to forget" description="Describe what you want removed. Vachan finds matching memories by meaning and deletes them permanently.">
        <form className="inline-form wide" onSubmit={forget}>
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. the loan from Arjun" aria-label="What should Vachan forget?" />
          <Button variant="danger" icon={Trash2} disabled={busy || !text.trim()}>{busy ? 'Forgetting…' : 'Forget'}</Button>
        </form>
        {result && <p className="result-note">{result.replace(/^\p{Extended_Pictographic}️?\s*/u, '')}</p>}
        <p className="muted small">You can also say it to Omi: “Hey Vachan, forget what I said about the loan.”</p>
      </Card>

      <Card title="How your data is protected" description="Privacy is enforced in code at every step, not just promised.">
        <div className="protections">
          {PROTECTIONS.map(({ icon: Icon, title, text: body }) => (
            <div key={title} className="protection">
              <span className="protection-icon"><Icon size={18} /></span>
              <div>
                <strong>{title}</strong>
                <p>{body}</p>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Audit log" description="Every deletion and visibility change, newest first." padded={false}>
        {audit.length === 0 ? (
          <EmptyState icon={FileClock} title="Nothing logged yet">Deletions and privacy changes will be recorded here.</EmptyState>
        ) : (
          <table className="table">
            <thead><tr><th>When</th><th>Action</th><th>Details</th></tr></thead>
            <tbody>
              {audit.slice(0, 50).map((a, i) => {
                const k = ACTION[a.action] || { tone: 'neutral', label: a.action }
                return (
                  <tr key={i}>
                    <td className="nowrap">{fmtDateTime(a.at)}</td>
                    <td><Badge tone={k.tone}>{k.label}</Badge></td>
                    <td>
                      {a.action === 'delete'
                        ? `${a.ids?.length || 0} item(s) from ${a.collection}: ${a.reason}`
                        : `${a.collection} item set to ${a.visibility}`}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  )
}
