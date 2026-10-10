import { Bell, Brain, Handshake, LayoutDashboard, Menu, Moon, Plug, Search, ShieldCheck, Sun, Workflow } from 'lucide-react'
import { useVachan } from '../store.jsx'
import { hasConflict, isMine, isOpen } from '../api.js'
import { IconButton } from './ui.jsx'

export const PAGES = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard, title: 'Overview', desc: 'Everything you have promised, at a glance.' },
  { id: 'promises', label: 'Promises', icon: Handshake, title: 'Promises', desc: 'Commitments captured from your conversations.' },
  { id: 'activity', label: 'Agent activity', icon: Workflow, title: 'Agent activity', desc: 'Every step the Lyzr agents took, traced live.' },
  { id: 'memory', label: 'Memory', icon: Brain, title: 'Memory', desc: 'Your conversation memory, stored in Qdrant.' },
  { id: 'privacy', label: 'Privacy', icon: ShieldCheck, title: 'Privacy', desc: 'Control what is stored and what agents can see.' },
  { id: 'connections', label: 'Connections', icon: Plug, title: 'Connections', desc: 'Omi, Lyzr and Qdrant status and setup.' },
]

function ServiceStatus() {
  const { health, online } = useVachan()
  const agents = health ? Object.values(health.agents) : []
  const live = agents.filter((a) => a === 'lyzr').length
  const rows = [
    { name: 'Omi', ok: health?.omi === 'omi', text: health?.omi === 'omi' ? 'Connected' : 'Simulator mode' },
    { name: 'Lyzr', ok: live > 0, text: health ? (live ? `${live}/${agents.length} agents live` : 'Local agents') : '…' },
    { name: 'Qdrant', ok: !!health, text: health ? (health.qdrant === 'cloud' ? 'Cloud cluster' : 'Local storage') : '…' },
  ]
  return (
    <div className="service-status">
      <div className="service-head">
        <span>Services</span>
        <span className={`live ${online ? 'on' : online === null ? 'wait' : ''}`}>
          {online ? 'Live' : online === null ? 'Connecting' : 'Reconnecting'}
        </span>
      </div>
      {rows.map((r) => (
        <div key={r.name} className="service-row">
          <span className={`status-dot ${r.ok ? 'ok' : 'idle'}`} />
          <span className="service-name">{r.name}</span>
          <span className="service-text">{r.text}</span>
        </div>
      ))}
    </div>
  )
}

export function Sidebar({ page, onNavigate, open, onClose }) {
  const { commitments, runs } = useVachan()
  const openMine = commitments.filter((c) => isMine(c) && isOpen(c)).length
  const conflicts = commitments.filter(hasConflict).length
  const running = runs.some((r) => r.status === 'running')
  const counts = { promises: openMine || null }

  return (
    <>
      {open && <div className="sidebar-scrim" onClick={onClose} />}
      <nav className={`sidebar ${open ? 'open' : ''}`} aria-label="Main">
        <a className="brand" href="#/overview" onClick={onClose}>
          <span className="brand-mark" lang="hi">व</span>
          <span className="brand-text">
            <strong>Vachan</strong>
            <small>Your word, kept.</small>
          </span>
        </a>
        <ul className="nav">
          {PAGES.map((p) => {
            const Icon = p.icon
            return (
              <li key={p.id}>
                <a
                  href={`#/${p.id}`}
                  className={page === p.id ? 'active' : ''}
                  onClick={() => { onNavigate(p.id); onClose() }}
                  aria-current={page === p.id ? 'page' : undefined}
                >
                  <Icon size={18} strokeWidth={1.9} />
                  <span>{p.label}</span>
                  {p.id === 'overview' && conflicts > 0 && <span className="nav-count warn">{conflicts}</span>}
                  {counts[p.id] && <span className="nav-count">{counts[p.id]}</span>}
                  {p.id === 'activity' && running && <span className="nav-pulse" />}
                </a>
              </li>
            )
          })}
        </ul>
        <ServiceStatus />
      </nav>
    </>
  )
}

export function Topbar({ page, onAsk, onBell, onMenu, theme, onTheme }) {
  const { unread } = useVachan()
  const meta = PAGES.find((p) => p.id === page) || PAGES[0]
  return (
    <header className="topbar">
      <IconButton icon={Menu} label="Open menu" className="menu-btn" onClick={onMenu} />
      <div className="page-title">
        <h1>{meta.title}</h1>
        <p>{meta.desc}</p>
      </div>
      <button className="ask-trigger" onClick={onAsk}>
        <Search size={16} />
        <span>Ask Vachan…</span>
        <kbd>Ctrl K</kbd>
      </button>
      <IconButton icon={Bell} label="Notifications" onClick={onBell} badge={unread} />
      <IconButton icon={theme === 'dark' ? Sun : Moon} label={theme === 'dark' ? 'Light mode' : 'Dark mode'} onClick={onTheme} />
    </header>
  )
}
