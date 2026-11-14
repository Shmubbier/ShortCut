// First-visit onboarding: "Got a reviewer code?", then a spotlight tour over the ready-made ube video.
import { useEffect, useState, type CSSProperties } from 'react'

export function Welcome({ onYes, onNo, onSkip }: { onYes: () => void; onNo: () => void; onSkip: () => void }) {
  return (
    <div className="unlock-back">
      <div className="unlock welcome-card" role="dialog" aria-label="Welcome to ShortCut">
        <span className="welcome-wave" aria-hidden="true">👋</span>
        <h2>Welcome to ShortCut</h2>
        <p>Topic in, short video out. First things first: do you have a reviewer code?</p>
        <div className="welcome-choices">
          <button className="primary" onClick={onYes} autoFocus>Yes, I have a code</button>
          <button className="ghost" onClick={onNo}>No, just looking</button>
        </div>
        <button className="link" onClick={onSkip}>Skip the intro</button>
      </div>
    </div>
  )
}

type Step = { sel?: string; title: string; text: string }

export function Tour({ live, onDone }: { live: boolean; onDone: (toPrompt: boolean) => void }) {
  const steps: Step[] = [
    { sel: '.stage', title: 'Your video, live', text: 'Here is a finished short about ube. Press play and enjoy the purple.' },
    { sel: '.canvas .node', title: 'One card = one segment', text: 'Click a card to edit its words, voice and timing. Drag cards to reorder.' },
    { sel: '.canvas .oval', title: 'Modules dangle below', text: 'Image, voice, 3D and effects hang off each card. Drag new ones on, tap × to drop one.' },
    { sel: '.rail-btn[aria-label="Asset Library"]', title: 'Hunting for pictures?', text: 'Search images, clips and 3D models here, then drag them onto a card.' },
    { sel: '.assist-fab', title: 'Your AI sidekick ✦', text: `Ask for anything: “make it funnier”, “add a stat”. Select a card first to change only that one.${live ? '' : ' (Needs a reviewer code.)'}` },
    { sel: '.rail-btn[aria-label="Project Settings"]', title: 'Ship it', text: 'Export lives here: download the MP4 or save the project file.' },
    { sel: '.rail-btn[aria-label="Sources"]', title: 'Receipts, please', text: 'Every page the AI read and every picture’s credit, all in one tab.' },
    live
      ? { title: 'You’re all set!', text: 'Want to start creating your own video?' }
      : { title: 'That’s the end of the demo!', text: 'Want to try the jeepney or tower defense demos? Head back to the prompt page and ask about them.' },
  ]
  const [k, setK] = useState(0)
  const [box, setBox] = useState<DOMRect | null>(null)
  const step = steps[k]
  const last = k === steps.length - 1

  useEffect(() => { // track the target: the editor animates in and the window can resize mid-step
    const find = () => {
      const el = step.sel ? document.querySelector(step.sel) : null
      setBox(el ? el.getBoundingClientRect() : null)
    }
    find()
    const t = setInterval(find, 250)
    return () => clearInterval(t)
  }, [k]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onDone(false)
      if (e.key === 'ArrowRight' && !last) setK(k + 1)
      if (e.key === 'ArrowLeft' && k) setK(k - 1)
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [k, last, onDone])

  // Card to the right of the target, else left, below, above; if none fits (big target, small window), pinned bottom-centre.
  const W = 300, H = 220, gap = 16, vw = window.innerWidth, vh = window.innerHeight
  const clampX = (x: number) => Math.max(gap, Math.min(x, vw - W - gap))
  const clampY = (y: number) => Math.max(gap, Math.min(y, vh - H))
  let pos: CSSProperties = { left: '50%', top: '50%', transform: 'translate(-50%, -50%)' }
  if (box) {
    if (box.right + gap + W < vw - gap) pos = { left: box.right + gap, top: clampY(box.top) }
    else if (box.left - gap - W > gap) pos = { left: box.left - gap - W, top: clampY(box.top) }
    else if (box.bottom + gap + H < vh) pos = { left: clampX(box.left), top: box.bottom + gap }
    else if (box.top - gap - H > 0) pos = { left: clampX(box.right - W), bottom: vh - box.top + gap }
    else pos = { left: '50%', bottom: gap, transform: 'translateX(-50%)' }
  }
  const pad = 8
  return (
    <div className="tour" role="dialog" aria-label="Tour" aria-live="polite">
      <div className={`tour-dim ${box ? '' : 'full'}`} />
      {box && <div className="tour-spot" style={{ left: box.left - pad, top: box.top - pad, width: box.width + pad * 2, height: box.height + pad * 2 }} />}
      <div className="tour-card" style={{ ...pos, width: W }}>
        <small className="tour-count">{k + 1} / {steps.length}</small>
        <h3>{step.title}</h3>
        <p>{step.text}</p>
        <div className="tour-actions">
          {last ? (
            <>
              <button className="ghost" onClick={() => onDone(false)}>{live ? 'Look around first' : 'Stay here'}</button>
              <button className="primary" onClick={() => onDone(true)} autoFocus>{live ? 'Start creating' : 'Back to the prompt page'}</button>
            </>
          ) : (
            <>
              <button className="link" onClick={() => onDone(false)}>Skip</button>
              {k > 0 && <button className="ghost" onClick={() => setK(k - 1)}>Back</button>}
              <button className="primary" onClick={() => setK(k + 1)} autoFocus>Next</button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
