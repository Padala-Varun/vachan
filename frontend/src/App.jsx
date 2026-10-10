import { useCallback, useEffect, useState } from 'react'
import { useVachan, VachanProvider } from './store.jsx'
import { PAGES, Sidebar, Topbar } from './components/Shell.jsx'
import AskPalette from './components/AskPalette.jsx'
import NotificationsDrawer from './components/NotificationsDrawer.jsx'
import PromiseDrawer from './components/PromiseDrawer.jsx'
import { Toasts } from './components/ui.jsx'
import Overview from './pages/Overview.jsx'
import Promises from './pages/Promises.jsx'
import Activity from './pages/Activity.jsx'
import Memory from './pages/Memory.jsx'
import Privacy from './pages/Privacy.jsx'
import Connections from './pages/Connections.jsx'

const pageFromHash = () => {
  const id = window.location.hash.replace(/^#\/?/, '')
  return PAGES.some((p) => p.id === id) ? id : 'overview'
}

function readTheme() {
  try {
    const saved = localStorage.getItem('vachan-theme')
    if (saved) return saved
  } catch { /* storage unavailable */ }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function Layout() {
  const { toasts, dismissToast, markNotificationsSeen } = useVachan()
  const [page, setPage] = useState(pageFromHash)
  const [theme, setTheme] = useState(readTheme)
  const [menuOpen, setMenuOpen] = useState(false)
  const [askOpen, setAskOpen] = useState(false)
  const [bellOpen, setBellOpen] = useState(false)
  const [promise, setPromise] = useState(null)
  const [selectedRun, setSelectedRun] = useState(null)

  // leaving a page closes any panel opened on it
  useEffect(() => { setPromise(null); setBellOpen(false) }, [page])

  useEffect(() => {
    const onHash = () => setPage(pageFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem('vachan-theme', theme) } catch { /* ignore */ }
  }, [theme])

  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setAskOpen((v) => !v)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const navigate = useCallback((id) => {
    window.location.hash = `/${id}`
    setPage(id)
    window.scrollTo({ top: 0 })
  }, [])

  const openRun = useCallback((id) => {
    setSelectedRun(id)
    navigate('activity')
  }, [navigate])

  const shared = { onNavigate: navigate, onOpenPromise: setPromise, onOpenRun: openRun }

  return (
    <div className="layout">
      <Sidebar page={page} onNavigate={navigate} open={menuOpen} onClose={() => setMenuOpen(false)} />
      <div className="main">
        <Topbar
          page={page}
          onAsk={() => setAskOpen(true)}
          onBell={() => { setBellOpen(true); markNotificationsSeen() }}
          onMenu={() => setMenuOpen(true)}
          theme={theme}
          onTheme={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
        />
        <main className="content" id="content">
          {page === 'overview' && <Overview {...shared} />}
          {page === 'promises' && <Promises {...shared} />}
          {page === 'activity' && <Activity selectedRun={selectedRun} onSelectRun={setSelectedRun} onNavigate={navigate} />}
          {page === 'memory' && <Memory />}
          {page === 'privacy' && <Privacy />}
          {page === 'connections' && <Connections onNavigate={navigate} />}
        </main>
      </div>

      <AskPalette open={askOpen} onClose={() => setAskOpen(false)} onOpenRun={openRun} />
      <NotificationsDrawer open={bellOpen} onClose={() => setBellOpen(false)} />
      <PromiseDrawer promise={promise} onClose={() => setPromise(null)} />
      <Toasts toasts={toasts} onDismiss={dismissToast} />
    </div>
  )
}

export default function App() {
  return (
    <VachanProvider>
      <Layout />
    </VachanProvider>
  )
}
