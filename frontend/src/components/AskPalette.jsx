import AskBox from './AskBox.jsx'
import { Modal } from './ui.jsx'

/** Popup version of the ask box (Ctrl+K, the top button, or the floating mic). */
export default function AskPalette({ open, onClose, onOpenRun, initial = {} }) {
  return (
    <Modal open={open} onClose={onClose} width={640} className="palette">
      {open && (
        <AskBox
          key={`${initial.text || ''}-${initial.listen ? 'mic' : 'text'}-${initial.nonce || 0}`}
          variant="palette"
          initialText={initial.text}
          autoSubmit={!!initial.text}
          autoListen={!!initial.listen}
          onOpenRun={(id) => { onOpenRun(id); onClose() }}
        />
      )}
      <footer className="palette-foot">
        <span><kbd>Enter</kbd> to ask</span>
        <span><kbd>Esc</kbd> to close</span>
        <span className="muted">Same as saying “Hey Vachan…” to Omi</span>
      </footer>
    </Modal>
  )
}
