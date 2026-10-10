import { useMemo, useState } from 'react'
import { Handshake, Search, X } from 'lucide-react'
import { hasConflict, isMine } from '../api.js'
import { useVachan } from '../store.jsx'
import PromiseRow from '../components/PromiseRow.jsx'
import { Avatar, Card, EmptyState, Segmented } from '../components/ui.jsx'

const SECTIONS = [
  { key: 'attention', title: 'Needs attention', test: (c) => c.status === 'open' && (c.urgency === 'overdue' || hasConflict(c)) },
  { key: 'soon', title: 'Due within 24 hours', test: (c) => c.status === 'open' && c.urgency === 'soon' },
  { key: 'later', title: 'Later', test: (c) => c.status === 'open' && c.urgency === 'later' },
  { key: 'none', title: 'No deadline', test: (c) => c.status === 'open' && c.urgency === 'none' },
  { key: 'done', title: 'Kept', test: (c) => c.status === 'done' },
]

export default function Promises({ onOpenPromise }) {
  const { commitments, loaded } = useVachan()
  const [owner, setOwner] = useState('me')
  const [status, setStatus] = useState('open')
  const [query, setQuery] = useState('')
  const [person, setPerson] = useState(null)

  const people = useMemo(() => [...new Set(commitments.map((c) => c.counterparty).filter(Boolean))].sort(), [commitments])
  const q = query.trim().toLowerCase()
  const filtered = commitments.filter((c) =>
    (owner === 'all' || (owner === 'me' ? isMine(c) : !isMine(c))) &&
    (status === 'all' || c.status === status) &&
    (!person || c.counterparty === person) &&
    (!q || `${c.action} ${c.counterparty} ${c.quote}`.toLowerCase().includes(q)))

  const count = (o) => commitments.filter((c) => c.status === 'open' && (o === 'me' ? isMine(c) : !isMine(c))).length
  const used = new Set()

  return (
    <div className="stack">
      <div className="toolbar">
        <Segmented
          value={owner}
          onChange={setOwner}
          options={[
            { value: 'me', label: 'I owe', count: count('me') },
            { value: 'other', label: 'Owed to me', count: count('other') },
            { value: 'all', label: 'All' },
          ]}
        />
        <Segmented
          value={status}
          onChange={setStatus}
          options={[{ value: 'open', label: 'Open' }, { value: 'done', label: 'Kept' }, { value: 'all', label: 'Any status' }]}
        />
        <label className="search-field">
          <Search size={16} />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search promises" aria-label="Search promises" />
          {query && <button onClick={() => setQuery('')} aria-label="Clear search"><X size={14} /></button>}
        </label>
      </div>

      {people.length > 0 && (
        <div className="people-filter" aria-label="Filter by person">
          <button className={!person ? 'active' : ''} onClick={() => setPerson(null)}>Everyone</button>
          {people.map((p) => (
            <button key={p} className={person === p ? 'active' : ''} onClick={() => setPerson(person === p ? null : p)}>
              <Avatar name={p} size={20} /> {p}
            </button>
          ))}
        </div>
      )}

      <Card padded={false}>
        {loaded && filtered.length === 0 ? (
          <EmptyState icon={Handshake} title={commitments.length ? 'No promises match these filters' : 'No promises yet'}>
            {commitments.length ? 'Try another filter or clear the search.' : 'Promises appear here automatically after a conversation with Omi.'}
          </EmptyState>
        ) : (
          SECTIONS.map((s) => {
            const items = filtered.filter((c) => !used.has(c.id) && s.test(c))
            items.forEach((c) => used.add(c.id))
            if (!items.length) return null
            return (
              <div key={s.key} className={`section section-${s.key}`}>
                <h3 className="section-title">{s.title}<span>{items.length}</span></h3>
                <ul className="promise-list">{items.map((c) => <PromiseRow key={c.id} c={c} onOpen={onOpenPromise} />)}</ul>
              </div>
            )
          })
        )}
      </Card>
    </div>
  )
}
