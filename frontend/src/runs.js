// Turns the flat trace event stream into runs with ordered, explained steps.

export const STEP_INFO = {
  privacy_prepass: { label: 'Mask personal data', desc: 'Phone numbers, emails, IDs and off-the-record speech are removed on this machine.' },
  privacy_guard: { label: 'Privacy Guard', desc: 'Redacts health and money details and labels how sensitive each part is.' },
  qdrant_store_transcript: { label: 'Save conversation memory', desc: 'Stores the redacted conversation in Qdrant with local embeddings.' },
  extractor: { label: 'Promise Extractor', desc: 'Finds who promised what to whom, and by when.' },
  verify_extraction: { label: 'Verify dates & people', desc: 'Re-checks every deadline and name against the transcript, in code.' },
  qdrant_retrieve_context: { label: 'Look up related promises', desc: 'Vector search for similar promises plus a filter for the same day.' },
  curator: { label: 'Curator & Conflict Detector', desc: 'Decides new, update or duplicate, and checks for schedule clashes.' },
  verify_decisions: { label: 'Verify decisions', desc: 'Checks duplicates against Qdrant results and catches any missed time clash.' },
  qdrant_write_commitments: { label: 'Save promises', desc: 'Writes the curated promises to the Qdrant commitments collection.' },
  nudger: { label: 'Nudger', desc: 'Writes short, friendly phone notifications.' },
  verify_notifications: { label: 'Verify notifications', desc: 'Checks every day and time in a message against the real deadline.' },
  omi_notify: { label: 'Send to phone', desc: 'Delivers the notifications through the Omi app.' },
  router: { label: 'Router', desc: 'Understands the request and picks the right specialist.' },
  recall: { label: 'Recall', desc: 'Answers using only the memories retrieved from Qdrant.' },
  qdrant_recall: { label: 'Search memory', desc: 'Filtered vector search over promises and conversations.' },
  qdrant_mark_done: { label: 'Mark promise as kept', desc: 'Finds the matching open promise and closes it.' },
  qdrant_forget: { label: 'Forget memories', desc: 'Deletes matching memories from Qdrant and logs it.' },
  pipeline: { label: 'Run promise pipeline', desc: 'Sends the dictated promise through the full pipeline.' },
}

export const PIPELINE = [
  'privacy_prepass', 'privacy_guard', 'qdrant_store_transcript', 'extractor',
  'verify_extraction', 'qdrant_retrieve_context', 'curator', 'verify_decisions', 'qdrant_write_commitments', 'nudger', 'verify_notifications', 'omi_notify',
]

export function buildRuns(events) {
  const runs = new Map()
  for (const ev of events) {
    if (!ev.run_id) continue
    let run = runs.get(ev.run_id)
    if (!run) {
      run = { id: ev.run_id, kind: 'command', title: '', status: 'running', started: ev.ts, steps: [], notes: [] }
      runs.set(ev.run_id, run)
    }
    if (ev.type === 'run_start') {
      Object.assign(run, { kind: ev.kind, title: ev.title, started: ev.ts, source: ev.source })
    } else if (ev.type === 'run_end') {
      Object.assign(run, { status: ev.status, ended: ev.ts, result: ev })
    } else if (ev.type === 'step_start') {
      run.steps.push({ id: ev.span_id, step: ev.step, kind: ev.kind, status: 'running', input: ev.input, ts: ev.ts })
    } else if (ev.type === 'step_end') {
      const s = run.steps.find((x) => x.id === ev.span_id)
      if (s) Object.assign(s, { status: ev.status, output: ev.output, error: ev.error, latency: ev.latency_ms, backend: ev.backend })
    } else if (ev.type === 'notification') {
      run.notes.push(ev)
    }
  }
  return [...runs.values()].sort((a, b) => new Date(b.started) - new Date(a.started))
}

// Steps to show: for conversations, the full pipeline with not-yet-run steps as pending.
export function runSteps(run) {
  if (run.kind !== 'conversation') return run.steps
  const shown = [...run.steps]
  for (const step of PIPELINE) {
    if (!run.steps.some((s) => s.step === step)) {
      const kind = step.startsWith('qdrant') ? 'qdrant' : step === 'omi_notify' ? 'omi'
        : ['privacy_prepass', 'verify_extraction', 'verify_decisions', 'verify_notifications'].includes(step) ? 'local' : 'agent'
      shown.push({ id: `pending-${step}`, step, kind, status: run.status === 'running' ? 'pending' : 'skipped' })
    }
  }
  return shown
}
