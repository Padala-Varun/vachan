import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, Info, X } from 'lucide-react'

export function Button({ variant = 'secondary', size = 'md', icon: Icon, children, className = '', ...props }) {
  return (
    <button className={`btn btn-${variant} btn-${size} ${className}`} {...props}>
      {Icon && <Icon size={size === 'sm' ? 14 : 16} strokeWidth={2} aria-hidden="true" />}
      {children}
    </button>
  )
}

export function IconButton({ icon: Icon, label, className = '', badge, ...props }) {
  return (
    <button className={`icon-btn ${className}`} aria-label={label} title={label} {...props}>
      <Icon size={18} strokeWidth={1.9} aria-hidden="true" />
      {badge ? <span className="icon-badge">{badge > 9 ? '9+' : badge}</span> : null}
    </button>
  )
}

export function Badge({ tone = 'neutral', icon: Icon, children, title }) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {Icon && <Icon size={12} strokeWidth={2.2} aria-hidden="true" />}
      {children}
    </span>
  )
}

const AVATAR_TONES = ['indigo', 'teal', 'amber', 'rose', 'violet', 'sky', 'emerald']
export function Avatar({ name, size = 32 }) {
  const label = (name || '?').trim()
  const tone = AVATAR_TONES[[...label].reduce((a, ch) => a + ch.charCodeAt(0), 0) % AVATAR_TONES.length]
  return (
    <span className={`avatar avatar-${tone}`} style={{ width: size, height: size, fontSize: size * 0.42 }} title={label}>
      {label.slice(0, 1).toUpperCase()}
    </span>
  )
}

export function Card({ title, description, actions, children, className = '', padded = true }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          <div>
            {title && <h2 className="card-title">{title}</h2>}
            {description && <p className="card-desc">{description}</p>}
          </div>
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      <div className={padded ? 'card-body' : ''}>{children}</div>
    </section>
  )
}

export function EmptyState({ icon: Icon, title, children, action }) {
  return (
    <div className="empty">
      {Icon && <div className="empty-icon"><Icon size={22} strokeWidth={1.8} /></div>}
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  )
}

export function Switch({ checked, onChange, label, disabled }) {
  return (
    <label className={`switch ${disabled ? 'disabled' : ''}`}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="switch-track"><span className="switch-thumb" /></span>
      {label && <span className="switch-label">{label}</span>}
    </label>
  )
}

export function Segmented({ value, onChange, options }) {
  return (
    <div className="segmented" role="tablist">
      {options.map((o) => (
        <button key={o.value} role="tab" aria-selected={value === o.value} className={value === o.value ? 'active' : ''} onClick={() => onChange(o.value)}>
          {o.label}
          {o.count != null && <span className="seg-count">{o.count}</span>}
        </button>
      ))}
    </div>
  )
}

function useEscape(open, onClose) {
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
}

export function Drawer({ open, onClose, title, subtitle, children, footer, width = 480 }) {
  useEscape(open, onClose)
  if (!open) return null
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside className="drawer" style={{ width }} role="dialog" aria-modal="true" aria-label={title}>
        <header className="drawer-head">
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <IconButton icon={X} label="Close" onClick={onClose} />
        </header>
        <div className="drawer-body">{children}</div>
        {footer && <footer className="drawer-foot">{footer}</footer>}
      </aside>
    </div>
  )
}

export function Modal({ open, onClose, children, width = 560, className = '' }) {
  useEscape(open, onClose)
  if (!open) return null
  return (
    <div className="overlay center" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${className}`} style={{ width }} role="dialog" aria-modal="true">{children}</div>
    </div>
  )
}

export function ConfirmDialog({ open, title, message, confirmLabel = 'Confirm', tone = 'danger', onConfirm, onClose }) {
  const [busy, setBusy] = useState(false)
  return (
    <Modal open={open} onClose={onClose} width={420}>
      <div className="confirm">
        <div className={`confirm-icon ${tone}`}><AlertTriangle size={20} /></div>
        <h3>{title}</h3>
        <p>{message}</p>
        <div className="confirm-actions">
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant={tone === 'danger' ? 'danger' : 'primary'}
            disabled={busy}
            onClick={async () => { setBusy(true); try { await onConfirm() } finally { setBusy(false); onClose() } }}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

const TOAST_ICON = { success: CheckCircle2, warning: AlertTriangle, danger: AlertTriangle, info: Info, neutral: Info }
export function Toasts({ toasts, onDismiss }) {
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => {
        const Icon = TOAST_ICON[t.tone] || Info
        return (
          <div key={t.id} className={`toast toast-${t.tone}`}>
            <Icon size={18} className="toast-icon" />
            <div className="toast-text">
              {t.title && <strong>{t.title}</strong>}
              <span>{t.message}</span>
            </div>
            <button className="toast-close" onClick={() => onDismiss(t.id)} aria-label="Dismiss"><X size={14} /></button>
          </div>
        )
      })}
    </div>
  )
}

export function JsonBlock({ value }) {
  if (value === undefined || value === null || value === '') return <p className="muted small">Nothing recorded.</p>
  let text = value
  if (typeof value === 'string') {
    try { text = JSON.stringify(JSON.parse(value), null, 2) } catch { text = value }
  } else {
    text = JSON.stringify(value, null, 2)
  }
  return <pre className="code">{text}</pre>
}

const REDACTED = /\[(PHONE|EMAIL|CARD|AADHAAR|PAN|OTP|HEALTH|FINANCE|ADDRESS|PRIVATE)\]/g

// Renders privacy placeholders like [FINANCE] as subtle "redacted" chips.
export function RedactedText({ text }) {
  if (!text) return null
  const parts = String(text).split(REDACTED)
  return parts.map((part, i) =>
    i % 2 === 1
      ? <span key={i} className="redacted" title="Removed for privacy before storage">{part.toLowerCase()}</span>
      : part)
}

export function Spinner({ size = 16 }) {
  return <span className="spinner" style={{ width: size, height: size }} aria-label="Loading" />
}
