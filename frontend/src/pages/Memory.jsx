import { useEffect, useMemo, useState } from 'react'
import { Brain, Lock, Search, Trash2, X } from 'lucide-react'
import { api, fmtDateTime } from '../api.js'
import { useVachan } from '../store.jsx'
import { Badge, Button, Card, ConfirmDialog, EmptyState, IconButton, RedactedText, Spinner, Switch } from '../components/ui.jsx'

const SENSITIVITY = {
  public: { tone: 'success', label: 'General' },
  personal: { tone: 'warning', label: 'Personal' },
  sensitive: { tone: 'danger', label: 'Sensitive' },
}

export default function Memory() {
  const { version, refresh, toast } = useVachan()
  const [query, setQuery] = useState('')
  const [active, setActive] = useState('')
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [toDelete, setToDelete] = useState(null)

  const load = async (q = active) => {
    setLoading(true)
    try { setItems(await api.memories(q)) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [version]) // eslint-disable-line react-hooks/exhaustive-deps

  const grouped = useMemo(() => {
    if (active) return [{ id: 'results', items }]
    const map = new Map()
    for (const m of items) {
      if (!map.has(m.conversation_id)) map.set(m.conversation_id, { id: m.conversation_id, started: m.started_at, items: [] })
      map.get(m.conversation_id).items.push(m)
    }
    const first = (m) => (m.segment_range || [0])[0]
    for (const g of map.values()) g.items.sort((a, b) => first(a) - first(b))
    return [...map.values()]
  }, [items, active])

  async function setPrivate(m, priv) {
    await api.patchMemory(m.id, { visibility: priv ? 'private' : 'shared' })
    toast(priv ? 'Memory is now private. Agents can no longer read it.' : 'Memory shared with your agents.', 'success')
    load()
  }

  const search = (e) => { e.preventDefault(); setActive(query.trim()); load(query.trim()) }
  const clear = () => { setQuery(''); setActive(''); load('') }

  return (
    <div className="stack">
      <form className="memory-search" onSubmit={search}>
        <Search size={18} />
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by meaning, e.g. “fundraising” or “dinner plans”" aria-label="Search memory" />
        {active && <IconButton icon={X} label="Clear search" type="button" onClick={clear} />}
        <Button variant="primary" type="submit">Search</Button>
      </form>
      <p className="muted small">
        Semantic search runs on Qdrant using embeddings computed on this machine. <Lock size={12} /> Private memories are
        searchable by you but never sent to any AI agent.
      </p>

      {loading && items.length === 0 ? (
        <div className="center-pad"><Spinner size={22} /></div>
      ) : items.length === 0 ? (
        <Card><EmptyState icon={Brain} title={active ? 'No matching memories' : 'No memories yet'}>{active ? 'Try different words: search works on meaning, not exact text.' : 'Conversations appear here after Omi captures them.'}</EmptyState></Card>
      ) : (
        grouped.map((g) => (
          <Card
            key={g.id}
            title={active ? `Results for “${active}”` : (g.items[0]?.speakers || []).filter((s) => s !== 'You').join(', ') || 'Conversation'}
            description={active ? `${items.length} best matches` : fmtDateTime(g.started)}
            padded={false}
          >
            <ul className="memory-list">
              {g.items.map((m) => {
                const s = SENSITIVITY[m.sensitivity] || SENSITIVITY.public
                return (
                  <li key={m.id} className={m.visibility === 'private' ? 'private' : ''}>
                    <div className="memory-meta">
                      <Badge tone={s.tone}>{s.label}</Badge>
                      {m.score != null && <Badge tone="info">{Math.round(m.score * 100)}% match</Badge>}
                      {active && <span className="muted small">{fmtDateTime(m.started_at)}</span>}
                      <div className="spacer" />
                      <Switch checked={m.visibility === 'private'} onChange={(v) => setPrivate(m, v)} label="Private" />
                      <IconButton icon={Trash2} label="Delete memory" className="danger" onClick={() => setToDelete(m)} />
                    </div>
                    <div className="memory-text">
                      {m.text.split('\n').map((line, i) => {
                        const idx = line.indexOf(': ')
                        return idx > 0
                          ? <p key={i}><b>{line.slice(0, idx)}</b> <RedactedText text={line.slice(idx + 2)} /></p>
                          : <p key={i}><RedactedText text={line} /></p>
                      })}
                    </div>
                  </li>
                )
              })}
            </ul>
          </Card>
        ))
      )}

      <ConfirmDialog
        open={!!toDelete}
        onClose={() => setToDelete(null)}
        title="Delete this memory?"
        message="This part of the conversation is permanently removed from Qdrant. The deletion is recorded in your audit log."
        confirmLabel="Delete memory"
        onConfirm={async () => { await api.deleteMemory(toDelete.id); toast('Memory deleted.', 'neutral'); load(); refresh() }}
      />
    </div>
  )
}
