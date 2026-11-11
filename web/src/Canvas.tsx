import { Thumbnail } from '@remotion/player'
import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { dims, EFFECTS, FPS, IMPORTANCE, Main, OVERLAP, planDuration, sceneStarts, timing, TRANSITIONS, type Effect, type Importance, type Plan } from './video/Video'

type Props = {
  plan: Plan
  sel: number | null
  onToggle: (i: number) => void
  onClear: () => void
  onReorder: (from: number, to: number) => void
  onDropItem: (i: number, json: string) => void
  onRemoveEffect: (i: number, e: Effect) => void
  onRemoveAsset: (i: number) => void
  onImportance: (i: number, level: Importance) => void
}
type View = { x: number; y: number; z: number }
type Gesture =
  | { kind: 'pan'; sx: number; sy: number; vx: number; vy: number; moved: boolean }
  | { kind: 'node'; i: number; ox: number; oy: number; sx: number; sy: number; moved: boolean }

// Milanote-style board: drag empty space (or scroll) to pan, Ctrl/⌘+scroll to zoom.
// Segments sit on one straight timeline; drag a card along it to reorder.
export function Canvas(props: Props) {
  const { plan, sel } = props
  const { w, h } = dims(plan)
  const nodeW = h > w ? 160 : 230
  const SLOT = nodeW + 110
  const thumbH = ((nodeW - 20) * h) / w
  const cardH = 34 + thumbH + 50 + 26 // header + thumbnail + two-line headline + timing row (fixed, so the strings know where cards end)
  const lens = plan.scenes.map((s) => timing(s, plan.pace))
  const longest = Math.max(...lens.map((l) => l.frames), 1)
  const wireY = 34 + thumbH / 2 // middle of the thumbnail
  const n = plan.scenes.length
  const starts = sceneStarts(plan)

  const box = useRef<HTMLDivElement>(null)
  const [view, setView] = useState<View>({ x: 40, y: 40, z: 1 })
  const [drag, setDrag] = useState<{ i: number; x: number; y: number } | null>(null)
  const [over, setOver] = useState<number | null>(null)
  const g = useRef<Gesture | null>(null)
  const live = useRef({ view, drag, props, SLOT, n })
  live.current = { view, drag, props, SLOT, n }

  const target = (x: number) => Math.max(0, Math.min(n - 1, Math.round(x / SLOT)))

  const fit = useCallback(() => {
    const el = box.current
    if (!el) return
    const z = Math.min(1, Math.max(0.3, (el.clientWidth - 80) / (n * SLOT - 110)))
    setView({ z, x: 40, y: 36 })
  }, [n, SLOT])
  useEffect(fit, [fit])

  const toWorld = (cx: number, cy: number) => {
    const r = box.current!.getBoundingClientRect()
    const v = live.current.view
    return { x: (cx - r.left - v.x) / v.z, y: (cy - r.top - v.y) / v.z }
  }

  useEffect(() => {
    const el = box.current!
    const move = (e: PointerEvent) => {
      const gs = g.current
      if (!gs) return
      if (Math.hypot(e.clientX - gs.sx, e.clientY - gs.sy) > 4) gs.moved = true
      if (!gs.moved) return
      if (gs.kind === 'pan') setView((v) => ({ ...v, x: gs.vx + e.clientX - gs.sx, y: gs.vy + e.clientY - gs.sy }))
      else {
        const p = toWorld(e.clientX, e.clientY)
        setDrag({ i: gs.i, x: p.x - gs.ox, y: p.y - gs.oy })
      }
    }
    const up = () => {
      const gs = g.current
      const { drag: d, props: p, SLOT: slot, n: count } = live.current
      g.current = null
      if (!gs) return
      if (gs.kind === 'pan' && !gs.moved) p.onClear()
      if (gs.kind === 'node' && !gs.moved) p.onToggle(gs.i)
      if (gs.kind === 'node' && gs.moved && d) p.onReorder(gs.i, Math.max(0, Math.min(count - 1, Math.round(d.x / slot))))
      setDrag(null)
    }
    const wheel = (e: WheelEvent) => {
      e.preventDefault()
      setView((v) => {
        if (!(e.ctrlKey || e.metaKey)) return { ...v, x: v.x - e.deltaX - (e.shiftKey ? e.deltaY : 0), y: v.y - (e.shiftKey ? 0 : e.deltaY) }
        const r = el.getBoundingClientRect()
        const px = e.clientX - r.left
        const py = e.clientY - r.top
        const z = Math.min(2, Math.max(0.3, v.z * Math.exp(-e.deltaY * 0.002)))
        return { z, x: px - ((px - v.x) * z) / v.z, y: py - ((py - v.y) * z) / v.z }
      })
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    el.addEventListener('wheel', wheel, { passive: false })
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      el.removeEventListener('wheel', wheel)
    }
  }, [])

  // Where each scene sits on the timeline right now (live preview while dragging).
  const order = plan.scenes.map((_, i) => i)
  if (drag) {
    order.splice(order.indexOf(drag.i), 1)
    order.splice(target(drag.x), 0, drag.i)
  }
  const slotOf = (i: number) => order.indexOf(i)

  const zoomBy = (k: number) => setView((v) => {
    const el = box.current!
    const cx = el.clientWidth / 2
    const cy = el.clientHeight / 2
    const z = Math.min(2, Math.max(0.3, v.z * k))
    return { z, x: cx - ((cx - v.x) * z) / v.z, y: cy - ((cy - v.y) * z) / v.z }
  })

  return (
    <div
      ref={box}
      className="canvas"
      style={{ backgroundPosition: `${view.x}px ${view.y}px`, backgroundSize: `${18 * view.z}px ${18 * view.z}px` }}
      onPointerDown={(e) => {
        if (e.button !== 0) return
        g.current = { kind: 'pan', sx: e.clientX, sy: e.clientY, vx: view.x, vy: view.y, moved: false }
      }}
    >
      <div className="world" style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.z})` }}>
        {order.slice(1).map((sceneIdx, k) => (
          <div key={`w${k}`} className="wire" style={{ left: k * SLOT + nodeW, top: wireY, width: SLOT - nodeW }}>
            <span>{TRANSITIONS[plan.scenes[sceneIdx].transition]}</span>
          </div>
        ))}
        {plan.scenes.map((s, i) => {
          const dragging = drag?.i === i
          const x = dragging ? drag.x : slotOf(i) * SLOT
          const y = dragging ? drag.y : 0
          // Tags float below the card as ovals on curved strings, like nodes hanging off their parent.
          const tags: { key: string; label: string; img?: string; remove?: () => void }[] = [
            ...(s.asset ? [{ key: 'asset', label: 'Image', img: s.asset, remove: () => props.onRemoveAsset(i) }] : []),
            ...(plan.style === '3d' && s.prop ? [{ key: 'prop', label: `3D · ${s.prop.name}` }] : []),
            ...(s.audio ? [{ key: 'voice', label: `Voice ${s.audio.duration.toFixed(1)}s` }] : []),
            ...s.effects.map((e) => ({ key: e, label: EFFECTS[e], remove: () => props.onRemoveEffect(i, e) })),
          ]
          const cx = x + nodeW / 2
          const tagAt = (k: number) => ({ x: cx + (k % 2 ? 34 : -34), y: y + cardH + 38 + k * 40 })
          return (
            <Fragment key={s.id ?? i}>
            {tags.length > 0 && (
              <svg className={`strings ${dragging ? 'dragging' : ''}`} width="1" height="1">
                {tags.map((tag, k) => {
                  const p = tagAt(k)
                  return <path key={tag.key} d={`M${cx},${y + cardH} C${cx},${y + cardH + 24} ${p.x},${p.y - 30} ${p.x},${p.y - 13}`} />
                })}
              </svg>
            )}
            {tags.map((tag, k) => {
              const p = tagAt(k)
              return (
                <span key={tag.key} className={`oval ${dragging ? 'dragging' : ''}`} style={{ transform: `translate(${p.x}px, ${p.y}px) translate(-50%, -50%)` }}
                  onPointerDown={(e) => e.stopPropagation()}>
                  {tag.img && <img src={tag.img} alt="" />}{tag.label}
                  {tag.remove && <button className="x" onClick={tag.remove} aria-label={`Remove ${tag.label}`}>×</button>}
                </span>
              )
            })}
            <div
              className={`node ${sel === i ? 'sel' : ''} ${over === i ? 'over' : ''} ${dragging ? 'dragging' : ''}`}
              style={{ width: nodeW, height: cardH, transform: `translate(${x}px, ${y}px)` }}
              onPointerDown={(e) => {
                if (e.button !== 0) return
                e.stopPropagation()
                const p = toWorld(e.clientX, e.clientY)
                g.current = { kind: 'node', i, ox: p.x - i * SLOT, oy: p.y, sx: e.clientX, sy: e.clientY, moved: false }
              }}
              onDragOver={(e) => { e.preventDefault(); setOver(i) }}
              onDragLeave={() => setOver(null)}
              onDrop={(e) => { e.preventDefault(); setOver(null); props.onDropItem(i, e.dataTransfer.getData('text/plain')) }}
            >
              <div className="nhead"><span>{String(slotOf(i) + 1).padStart(2, '0')}</span><em>{s.kind}</em></div>
              <Thumbnail component={Main} inputProps={plan} compositionWidth={w} compositionHeight={h}
                frameToDisplay={starts[i] + 30} durationInFrames={planDuration(plan)} fps={FPS} style={{ width: '100%', pointerEvents: 'none' }} />
              <p>{s.value && <b>{s.value} </b>}{s.headline}</p>
              {/* Timing: length vs the longest segment, coloured by importance; dots set importance */}
              <div className={`meter imp${s.importance ?? 2} ${lens[i].source === 'manual' ? 'manual' : ''}`} title={`${((lens[i].frames - OVERLAP) / FPS).toFixed(1)}s · ${{ voice: 'from the voiceover', script: 'from script length', manual: 'fixed by you' }[lens[i].source]} · ${IMPORTANCE[s.importance ?? 2].label}`}>
                <span className="secs">{((lens[i].frames - OVERLAP) / FPS).toFixed(1)}s</span>
                <span className="bar"><i style={{ width: `${(lens[i].frames / longest) * 100}%` }} /></span>
                <span className="pips" onPointerDown={(e) => e.stopPropagation()}>
                  {([1, 2, 3] as Importance[]).map((lv) => (
                    <button key={lv} className={lv <= (s.importance ?? 2) ? 'on' : ''} onClick={() => props.onImportance(i, lv)}
                      aria-label={`Importance: ${IMPORTANCE[lv].label}`} title={IMPORTANCE[lv].label} />
                  ))}
                </span>
              </div>
            </div>
            </Fragment>
          )
        })}
      </div>
      <div className="zoombar" onPointerDown={(e) => e.stopPropagation()}>
        <button onClick={() => zoomBy(1 / 1.2)} aria-label="Zoom out">−</button>
        <span>{Math.round(view.z * 100)}%</span>
        <button onClick={() => zoomBy(1.2)} aria-label="Zoom in">+</button>
        <button onClick={fit}>Fit</button>
      </div>
      <div className="canvas-tip">Drag cards to reorder · drag space to pan · Ctrl+scroll to zoom</div>
    </div>
  )
}
