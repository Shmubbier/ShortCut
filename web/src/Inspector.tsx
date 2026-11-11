// Segment inspector: slides in from the right when a segment is selected and stays open until collapsed (spec §5).
// It edits the same scene fields the Script panel shows, so narration edits sync both ways.
import { useEffect, useState } from 'react'
import { spans, stamp } from './Panels'
import type { Recipe } from './video/bench3d/recipe'
import { build, loadWasm } from './video/Stage3D'
import { FPS, IMPORTANCE, MAX_LEN, MIN_LEN, OVERLAP, ROLES, isEmpty, sceneLen, timing, type Importance, type Plan, type Role, type SceneData } from './video/Video'

type Props = {
  plan: Plan
  sel: number | null
  onClose: () => void
  change: (p: Plan) => void // live edit (typing): undo groups a burst of edits
  snapshot: () => void // call once before a discrete edit to make it undoable
  voice: (i: number | null) => void
  busy: string
  fixProp: (i: number, error: string) => void
  findImages: (query: string, assignTo: number | null) => void
  fixLength: (i: number, seconds: number) => void // ask the AI to rewrite a segment's voiceover to fit a fixed length
  fill: (i: number) => void // ask the AI to write an empty segment
  remove: (i: number) => void
  clipFor: (i: number, clip: { url: string; name: string; duration?: number }) => void // put a library video clip on segment i
}

// 3D prop build errors, checked with the same builder the renderer uses.
function usePropError(prop: Recipe | null | undefined) {
  const [err, setErr] = useState<string>()
  useEffect(() => {
    if (!prop) return setErr(undefined)
    loadWasm().then((w) => setErr(build(w, prop).error))
  }, [prop])
  return err
}

const secs = (frames: number) => `${(frames / FPS).toFixed(1)}s`
const round1 = (n: number) => Math.round(n * 10) / 10

export function Inspector(p: Props) {
  return (
    <aside className="inspector" aria-label="Segment inspector">
      <button className="collapse" onClick={p.onClose} aria-label="Collapse inspector" title="Collapse">›</button>
      {p.sel === null || !p.plan.scenes[p.sel]
        ? <p className="tip insp-empty">Select a segment on the storyboard to edit it here.</p>
        : <SegmentPanel {...p} i={p.sel} />}
    </aside>
  )
}

function SegmentPanel({ plan, i, change, snapshot, voice, busy, fixProp, findImages, fixLength, fill, remove, clipFor }: Props & { i: number }) {
  const s = plan.scenes[i]
  const propErr = usePropError(plan.style === '3d' ? s.prop : null)
  const set = (patch: Partial<SceneData>) => change({ ...plan, scenes: plan.scenes.map((x, j) => (j === i ? { ...x, ...patch } : x)) })
  const [capText, setCapText] = useState('')
  const [capErr, setCapErr] = useState('')
  const [dropping, setDropping] = useState(false)
  useEffect(() => { setCapText((s.words ?? []).map((w) => w.text).join(' ')); setCapErr('') }, [s.words])
  const times = spans(plan)
  const t = timing(s, plan.pace)
  const empty = isEmpty(s)

  function saveCaptions() {
    const toks = capText.trim().split(/\s+/).filter(Boolean)
    const words = s.words ?? []
    if (toks.length !== words.length) return setCapErr(`Keep ${words.length} words (you have ${toks.length}) so the timings still line up.`)
    snapshot()
    set({ words: words.map((w, k) => ({ ...w, text: toks[k] })) })
    setCapErr('')
  }
  // Start/end are views of segment lengths: moving this end resizes this segment; moving the start resizes the previous one.
  const setEnd = (end: number) => set({ length: Math.min(MAX_LEN, Math.max(MIN_LEN, round1(end - times[i].start))) })
  const setStart = (start: number) => {
    if (i === 0) return
    const len = Math.min(MAX_LEN, Math.max(MIN_LEN, round1(start - times[i - 1].start)))
    change({ ...plan, scenes: plan.scenes.map((x, j) => (j === i - 1 ? { ...x, length: len } : x)) })
  }

  return (
    <>
      <div className="seghead">
        <span className="seg-num">Segment {i + 1} of {plan.scenes.length}</span>
        <input className="seg-title" value={s.title ?? ''} placeholder={empty ? 'New segment' : s.headline || 'Untitled segment'}
          onChange={(e) => set({ title: e.target.value })} aria-label="Segment title" />
        <div className="row">
          <select value={s.role ?? ''} onChange={(e) => { snapshot(); set({ role: (e.target.value || undefined) as Role | undefined }) }} aria-label="Segment type">
            <option value="">Type…</option>
            {(Object.keys(ROLES) as Role[]).map((r) => <option key={r} value={r}>{ROLES[r]}</option>)}
          </select>
          <button className="danger" onClick={() => remove(i)} aria-label={`Delete segment ${i + 1}`}>Delete</button>
        </div>
      </div>

      {empty && (
        <div className="fill-box">
          This segment is empty. Write its narration and on-screen text below, drop an image on it, or
          <button onClick={() => fill(i)} disabled={!!busy}>{busy === 'ai' ? 'Writing…' : '✦ Fill with AI'}</button>
        </div>
      )}

      <label>Scene description<textarea rows={2} value={s.purpose ?? ''} placeholder="What happens in this scene and why" onChange={(e) => set({ purpose: e.target.value })} /></label>

      <h3>Narration</h3>
      <textarea rows={4} value={s.voiceover ?? ''} placeholder="What the narrator says over this segment"
        onChange={(e) => set({ voiceover: e.target.value, audio: null, words: [] })} aria-label="Narration" />
      <div className="row">
        <button onClick={() => voice(i)} disabled={!!busy || !s.voiceover?.trim()}>{busy === `voice-${i}` ? 'Voicing…' : s.audio ? 'Re-generate voice' : 'Generate voice'}</button>
        {s.audio && <audio src={s.audio.url} controls preload="none" />}
      </div>

      <h3>On-screen text</h3>
      <label>Headline<input value={s.headline} onChange={(e) => set({ headline: e.target.value })} /></label>
      <label>Subline<input value={s.sub} onChange={(e) => set({ sub: e.target.value })} /></label>
      {s.kind === 'stat' && <label>Number<input value={s.value} onChange={(e) => set({ value: e.target.value })} /></label>}

      <h3>Media</h3>
      <div className={`media-drop ${dropping ? 'over' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDropping(true) }} onDragLeave={() => setDropping(false)}
        onDrop={(e) => {
          e.preventDefault(); setDropping(false)
          try {
            const it = JSON.parse(e.dataTransfer.getData('text/plain'))
            if (it.type === 'asset') { snapshot(); set({ asset: it.url }) }
            if (it.type === 'clip') clipFor(i, it)
          } catch { /* not a library tile */ }
        }}>
        {s.media?.type === 'video' ? (
          // #t= media fragment previews just the trimmed slice in the browser's own player
          <video key={`${s.media.url}${s.media.trimStart}`} className="seg-img" src={`${s.media.url}#t=${s.media.trimStart ?? 0},${s.media.trimEnd ?? ''}`} controls muted preload="metadata" />
        ) : s.asset ? <img className="seg-img" src={s.asset} alt="" /> : <p className="tip">Drop an image or video clip from the Asset Library here.</p>}
      </div>
      {s.media?.type === 'video' && (
        <>
          <div className="row times">
            <label>Trim in<input type="number" step={0.1} min={0} max={s.media.duration} value={s.media.trimStart ?? 0} aria-label="Trim start, seconds into the clip"
              onChange={(e) => e.target.value && set({ media: { ...s.media!, trimStart: Math.max(0, Math.min(Number(e.target.value), (s.media!.trimEnd ?? 1e9) - 0.2)) } })} /></label>
            <label>Trim out<input type="number" step={0.1} min={0} max={s.media.duration} value={s.media.trimEnd ?? s.media.duration ?? 0} aria-label="Trim end, seconds into the clip"
              onChange={(e) => e.target.value && set({ media: { ...s.media!, trimEnd: Math.min(s.media!.duration ?? 1e9, Math.max(Number(e.target.value), (s.media!.trimStart ?? 0) + 0.2)) } })} /></label>
            <small className="tip">{s.media.name}{s.media.duration ? ` · ${s.media.duration.toFixed(1)}s clip` : ''}</small>
          </div>
          <div className="row">
            <button onClick={() => { snapshot(); set({ length: round1((s.media!.trimEnd ?? 0) - (s.media!.trimStart ?? 0)) }) }}>Fit duration to trim</button>
            <button className="link" onClick={() => { snapshot(); set({ media: null }) }}>Remove clip</button>
          </div>
        </>
      )}
      <div className="row">
        <button onClick={() => findImages(`${plan.title} ${s.headline || s.title || ''}`.trim(), i)} disabled={!!busy}>{busy === `find-${i}` ? 'Searching the web…' : 'Find images for this segment'}</button>
        {s.asset && <button className="link" onClick={() => { snapshot(); set({ asset: '' }) }}>Remove</button>}
      </div>

      <h3>Timing · {secs(t.frames - OVERLAP)}</h3>
      <div className="row times">
        <label>Start<input type="number" step={0.1} min={0} value={round1(times[i].start)} disabled={i === 0}
          onChange={(e) => e.target.value && setStart(Number(e.target.value))} aria-label="Start time, seconds" /></label>
        <label>End<input type="number" step={0.1} min={0} value={round1(times[i].end)}
          onChange={(e) => e.target.value && setEnd(Number(e.target.value))} aria-label="End time, seconds" /></label>
        <small className="tip">{stamp(times[i].start)}–{stamp(times[i].end)}</small>
      </div>
      <div className="imp-switch" role="group" aria-label="Duration preset">
        {([1, 2, 3] as Importance[]).map((lv) => (
          <button key={lv} className={!s.length && (s.importance ?? 2) === lv ? 'on' : ''} onClick={() => { snapshot(); set({ importance: lv, length: null }) }}>{IMPORTANCE[lv].label}</button>
        ))}
      </div>
      <label className="len-row">Duration
        <div className="row">
          <input type="range" min={MIN_LEN} max={MAX_LEN} step={0.1} value={s.length ?? (sceneLen(s, plan.pace) - OVERLAP) / FPS}
            onChange={(e) => set({ length: Number(e.target.value) })} aria-label="Segment duration in seconds" />
          <input type="number" min={MIN_LEN} max={MAX_LEN} step={0.1} className="secs-in" value={round1(s.length ?? (sceneLen(s, plan.pace) - OVERLAP) / FPS)}
            onChange={(e) => e.target.value && set({ length: Math.min(MAX_LEN, Math.max(MIN_LEN, Number(e.target.value))) })} aria-label="Segment duration, seconds" />
          {s.length ? <button className="link" onClick={() => { snapshot(); set({ length: null }) }}>Auto</button> : null}
        </div>
      </label>
      <small className="tip">{t.source === 'manual'
        ? `Fixed at ${s.length?.toFixed(1)}s. Later segments shift to match; press a preset or Auto to go back.`
        : t.source === 'voice'
          ? `${secs(t.voice)} of narration + ${secs(t.hold)} hold (${IMPORTANCE[s.importance ?? 2].label.toLowerCase()}).`
          : `From ${t.words} words of on-screen text (${IMPORTANCE[s.importance ?? 2].label.toLowerCase()}). Generate the voice to time it to the narration.`}</small>
      {t.cutsVoice && s.length ? (
        <div className="warn">
          The narration runs {secs(t.voice)}, longer than {s.length.toFixed(1)}s, so it'll be cut off.
          <div className="row">
            <button onClick={() => fixLength(i, s.length!)} disabled={!!busy}>Shorten the line to fit</button>
            <button className="link" onClick={() => { snapshot(); set({ length: Math.ceil((t.voice / FPS) * 10) / 10 + 0.3 }) }}>Use the narration's length</button>
          </div>
        </div>
      ) : null}

      <h3>Captions</h3>
      {s.words?.length ? (
        <>
          <textarea rows={3} value={capText} onChange={(e) => setCapText(e.target.value)} onBlur={saveCaptions} aria-label="Caption words" />
          <small className={capErr ? 'err' : 'tip'}>{capErr || (s.captionSource === 'whisper' ? 'Fix any misheard words; timings come from Whisper.' : 'Timings from the voice engine. Fix words freely.')}</small>
        </>
      ) : <p className="tip">Generate the voice to get word-timed captions.</p>}

      {(s.effects.length > 0 || s.transition !== 'cut') && (
        <>
          <h3>Tags</h3>
          <div className="chips-row">
            <span className="chip">In: {s.transition}</span>
            {s.effects.map((e) => <span key={e} className="chip">{e}</span>)}
          </div>
        </>
      )}

      {plan.style === '3d' && (
        <>
          <h3>3D prop</h3>
          {s.prop ? (
            <>
              <p className="tip">{s.prop.name}{s.prop.credit ? ` · ${s.prop.credit}` : ''}</p>
              {propErr && <><p className="err">Couldn't build: {propErr}</p><button onClick={() => fixProp(i, propErr)} disabled={!!busy}>Fix with AI</button></>}
              <button className="link" onClick={() => { snapshot(); set({ prop: null }) }}>Remove prop</button>
            </>
          ) : <p className="tip">No prop. Ask the assistant, e.g. "add a 3D jeepney here".</p>}
        </>
      )}
    </>
  )
}
