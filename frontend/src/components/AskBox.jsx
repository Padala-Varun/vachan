import { useEffect, useRef, useState } from 'react'
import { ArrowRight, CornerDownLeft, Mic, Send, Sparkles } from 'lucide-react'
import { api, fmtDue } from '../api.js'
import { useVachan } from '../store.jsx'
import { Avatar, Badge, RedactedText, Spinner } from './ui.jsx'

export const SUGGESTIONS = [
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

/**
 * The "talk to Vachan" experience: text or voice in, Router agent decides, answer out.
 * Used inline on the Overview page and inside the Ctrl+K popup.
 */
export default function AskBox({ variant = 'inline', initialText = '', autoSubmit = false, autoListen = false, onOpenRun }) {
  const { refresh } = useVachan()
  const [text, setText] = useState(initialText)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [listening, setListening] = useState(false)
  const inputRef = useRef(null)
  const recRef = useRef(null)

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

  function listen() {
    if (!Recognition) return
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
    setResult(null)
    setListening(true)
    rec.start()
  }

  useEffect(() => {
    if (autoSubmit && initialText) submit(initialText)
    else if (autoListen) listen()
    else if (variant === 'palette') setTimeout(() => inputRef.current?.focus(), 30)
    return () => recRef.current?.stop()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const intent = result && (INTENT[result.intent] || { label: 'Error', tone: 'danger' })

  return (
    <div className={`askbox askbox-${variant}`}>
      <form className="askbox-input" onSubmit={(e) => { e.preventDefault(); submit() }}>
        {Recognition && (
          <button
            type="button"
            className={`askbox-mic ${listening ? 'live' : ''}`}
            onClick={listen}
            aria-label={listening ? 'Stop listening' : 'Speak to Vachan'}
            title={listening ? 'Listening… click to stop' : 'Click and speak'}
          >
            <Mic size={variant === 'inline' ? 22 : 18} />
          </button>
        )}
        {!Recognition && <Sparkles size={18} className="askbox-spark" />}
        <input
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={listening ? 'Listening… speak now' : 'Ask about your promises, or tell Vachan something new'}
          aria-label="Ask Vachan"
        />
        {busy ? <Spinner /> : (
          <button type="submit" className="askbox-send" disabled={!text.trim()} aria-label="Ask">
            <Send size={16} />
          </button>
        )}
      </form>

      {!result && !busy && (
        variant === 'inline' ? (
          <div className="askbox-chips">
            {SUGGESTIONS.map((s) => (
              <button key={s.text} onClick={() => submit(s.text)}>
                <span className="chip-hint">{s.hint}</span>{s.text}
              </button>
            ))}
          </div>
        ) : (
          <div className="palette-body">
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
          </div>
        )
      )}

      {busy && <p className="askbox-thinking"><Spinner size={14} /> The Router agent is deciding who should answer…</p>}

      {result && (
        <div className="askbox-result">
          <div className="askbox-result-head">
            <Badge tone={intent.tone}>{intent.label}</Badge>
            <button className="link-btn small" onClick={() => { setResult(null); setText('') }}>Ask something else</button>
          </div>
          <p className="askbox-answer">{result.answer?.replace(/^\p{Extended_Pictographic}️?\s*/u, '')}</p>
          {result.matches?.length > 0 && (
            <ul className="mini-list">
              {result.matches.slice(0, 4).map((c) => (
                <li key={c.id}>
                  <Avatar name={c.counterparty} size={26} />
                  <div className="mini-text">
                    <strong><RedactedText text={c.action} /></strong>
                    <span>{c.owner === 'me' ? `You → ${c.counterparty || 'someone'}` : `${c.counterparty || 'Someone'} → You`} · {fmtDue(c.due_at)}</span>
                  </div>
                  {c.status === 'done' && <Badge tone="success">Kept</Badge>}
                </li>
              ))}
            </ul>
          )}
          {result.run_id && onOpenRun && (
            <button className="link-btn" onClick={() => onOpenRun(result.run_id)}>
              See how the agents answered <ArrowRight size={14} />
            </button>
          )}
        </div>
      )}
    </div>
  )
}
