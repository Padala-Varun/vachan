import { useEffect, useRef, useState } from 'react'
import { ArrowRight, CornerDownLeft, Mic, Sparkles } from 'lucide-react'
import { api, fmtDue } from '../api.js'
import { useVachan } from '../store.jsx'
import { Avatar, Badge, Modal, RedactedText, Spinner } from './ui.jsx'

const SUGGESTIONS = [
  { text: 'What do I owe Rahul this week?', hint: 'Recall' },
  { text: 'What did Priya promise me?', hint: 'Recall' },
  { text: 'I sent the pitch deck to Rahul', hint: 'Mark as kept' },
  { text: 'Remind me I promised Mom to call on Sunday', hint: 'Add promise' },
  { text: 'Forget what I said about the loan', hint: 'Delete memory' },
]

const INTENT = {
  recall: { label: 'Answer', tone: 'info' },
  mark_done: { label: 'Marked as kept', tone: 'success' },
  forget: { label: 'Forgotten', tone: 'danger' },
  add: { label: 'Promise added', tone: 'info' },
  unknown: { label: 'Not sure', tone: 'neutral' },
}

const Recognition = typeof window !== 'undefined' && (window.SpeechRecognition || window.webkitSpeechRecognition)

export default function AskPalette({ open, onClose, onOpenRun }) {
  const { refresh } = useVachan()
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [listening, setListening] = useState(false)
  const inputRef = useRef(null)
  const recRef = useRef(null)

  useEffect(() => {
    if (open) {
      setResult(null)
      setTimeout(() => inputRef.current?.focus(), 30)
    } else {
      recRef.current?.stop()
    }
  }, [open])

  async function submit(value, source = 'dashboard') {
    const q = (value ?? text).trim()
    if (!q || busy) return
    setText(q)
    setBusy(true)
    setResult(null)
    try {
      setResult(await api.ask(q, source))
    } catch (e) {
      setResult({ intent: 'error', answer: e.message })
    } finally {
      setBusy(false)
      refresh()
    }
  }

  function toggleMic() {
    if (listening) { recRef.current?.stop(); return }
    const rec = new Recognition()
    rec.lang = 'en-IN'
    rec.interimResults = true
    rec.onresult = (e) => {
      const transcript = [...e.results].map((r) => r[0].transcript).join('')
      setText(transcript)
      if (e.results[e.results.length - 1].isFinal) submit(transcript, 'dashboard-voice')
    }
    rec.onend = () => setListening(false)
    rec.onerror = () => setListening(false)
    recRef.current = rec
    setListening(true)
    rec.start()
  }

  const intent = result && (INTENT[result.intent] || { label: 'Error', tone: 'danger' })

  return (
    <Modal open={open} onClose={onClose} width={640} className="palette">
      <form className="palette-input" onSubmit={(e) => { e.preventDefault(); submit() }}>
        <Sparkles size={18} className="palette-icon" />
        <input
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={listening ? 'Listening…' : 'Ask about your promises, or tell Vachan something'}
          aria-label="Ask Vachan"
        />
        {busy && <Spinner />}
        {Recognition && (
          <button type="button" className={`palette-mic ${listening ? 'live' : ''}`} onClick={toggleMic} aria-label="Speak your question" title="Speak">
            <Mic size={16} />
          </button>
        )}
      </form>

      <div className="palette-body">
        {!result && !busy && (
          <>
            <p className="palette-section">Try saying</p>
            <ul className="palette-list">
              {SUGGESTIONS.map((s) => (
                <li key={s.text}>
                  <button onClick={() => submit(s.text)}>
                    <span>{s.text}</span>
                    <span className="palette-hint">{s.hint}</span>
                    <CornerDownLeft size={14} className="palette-enter" />
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}

        {busy && <p className="palette-thinking">The Router agent is working on it…</p>}

        {result && (
          <div className="palette-result">
            <Badge tone={intent.tone}>{intent.label}</Badge>
            <p className="palette-answer">{result.answer}</p>
            {result.matches?.length > 0 && (
              <ul className="mini-list">
                {result.matches.slice(0, 4).map((c) => (
                  <li key={c.id}>
                    <Avatar name={c.counterparty} size={26} />
                    <div>
                      <strong><RedactedText text={c.action} /></strong>
                      <span>{c.owner === 'me' ? `You → ${c.counterparty || 'someone'}` : `${c.counterparty || 'Someone'} → You`} · {fmtDue(c.due_at)}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {result.run_id && (
              <button className="link-btn" onClick={() => { onOpenRun(result.run_id); onClose() }}>
                See how the agents answered <ArrowRight size={14} />
              </button>
            )}
          </div>
        )}
      </div>
      <footer className="palette-foot">
        <span><kbd>Enter</kbd> to ask</span>
        <span><kbd>Esc</kbd> to close</span>
        <span className="muted">Same as saying “Hey Vachan…” to Omi</span>
      </footer>
    </Modal>
  )
}
