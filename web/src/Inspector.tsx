import { useEffect, useState } from 'react'
import type { Recipe } from './video/bench3d/recipe'
import { build, loadWasm } from './video/Stage3D'
import { FONTS, PALETTES, STYLES, resolveTheme } from './video/theme'
import { FPS, IMPORTANCE, sceneLen, timing, type Importance, type Plan, type SceneData } from './video/Video'

export const VOICES = [
  ['en-US-AndrewNeural', 'Andrew · US'], ['en-US-AvaNeural', 'Ava · US'], ['en-GB-RyanNeural', 'Ryan · UK'],
  ['en-PH-JamesNeural', 'James · PH English'], ['en-PH-RosaNeural', 'Rosa · PH English'],
  ['fil-PH-AngeloNeural', 'Angelo · Filipino'], ['fil-PH-BlessicaNeural', 'Blessica · Filipino'],
] as const

type Props = {
  plan: Plan
  sel: number | null
  setSel: (i: number | null) => void
  change: (p: Plan) => void // live edit (typing), no undo entry
  snapshot: () => void // call once before an edit to make it undoable
  voice: (i: number | null) => void
  busy: string
  fixProp: (i: number, error: string) => void
  findImages: (query: string, assignTo: number | null) => void
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

export function Inspector(p: Props) {
  return (
    <aside className="inspector">
      {p.sel === null ? <Overview {...p} /> : <SegmentPanel {...p} i={p.sel} />}
    </aside>
  )
}

function Overview({ plan, change, snapshot, setSel, voice, busy }: Props) {
  const t = resolveTheme(plan.style, plan.theme)
  const theme = (k: string, v: unknown) => { snapshot(); change({ ...plan, theme: { ...plan.theme, [k]: v } }) }
  const total = plan.scenes.reduce((a, s) => a + sceneLen(s, plan.pace), 0)
  const voiced = plan.scenes.filter((s) => s.audio).length
  return (
    <>
      <h2>Overview</h2>
      <label>Title<input value={plan.title} onChange={(e) => change({ ...plan, title: e.target.value })} /></label>

      <h3>Look</h3>
      <label>Pace
        <select value={plan.pace} onChange={(e) => { snapshot(); change({ ...plan, pace: e.target.value as Plan['pace'] }) }}>
          <option value="punchy">Punchy</option><option value="documentary">Documentary</option>
        </select>
      </label>
      <label>Color scheme
        <div className="swatches">
          {Object.entries(PALETTES).map(([k, pal]) => (
            <button key={k} className={(plan.theme?.palette ?? STYLES[plan.style].palette) === k ? 'sw on' : 'sw'} title={pal.label} aria-label={pal.label}
              onClick={() => theme('palette', k)}>
              {pal.bg.slice(0, 4).map((c, j) => <i key={j} style={{ background: c }} />)}
            </button>
          ))}
        </div>
      </label>
      <div className="row">
        <label>Accent<input type="color" value={t.accent} onChange={(e) => theme('accent', e.target.value)} /></label>
        <label>Grain<input type="range" min={0} max={0.4} step={0.02} value={t.grain} onChange={(e) => theme('grain', Number(e.target.value))} /></label>
      </div>
      <div className="row">
        <label>Heading font
          <select value={t.display} onChange={(e) => theme('display', e.target.value)}>{FONTS.map((f) => <option key={f}>{f}</option>)}</select>
        </label>
        <label>Body font
          <select value={t.body} onChange={(e) => theme('body', e.target.value)}>{FONTS.map((f) => <option key={f}>{f}</option>)}</select>
        </label>
      </div>
      {plan.theme && <button className="link" onClick={() => { snapshot(); change({ ...plan, theme: undefined }) }}>Reset to style defaults</button>}

      <h3>Voice & captions</h3>
      <label>Narrator
        <select value={plan.voice ?? VOICES[0][0]} onChange={(e) => { snapshot(); change({ ...plan, voice: e.target.value }) }}>
          {VOICES.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
        </select>
      </label>
      <label className="check"><input type="checkbox" checked={plan.captions !== false} onChange={(e) => { snapshot(); change({ ...plan, captions: e.target.checked }) }} /> Show captions</label>
      <button onClick={() => voice(null)} disabled={!!busy}>{busy === 'voice-all' ? 'Voicing…' : `Voice all segments (${voiced}/${plan.scenes.length} done)`}</button>

      <h3>Segments · {secs(total)}</h3>
      <ol className="seglist">
        {plan.scenes.map((s, i) => (
          <li key={s.id} onClick={() => setSel(i)}>
            <em>{s.kind}</em><span>{s.purpose || s.headline}</span>
            <span className="bar"><i className={`imp${s.importance ?? 2}`} style={{ width: `${(sceneLen(s, plan.pace) / Math.max(...plan.scenes.map((x) => sceneLen(x, plan.pace)))) * 100}%` }} /></span>
            <small>{secs(sceneLen(s, plan.pace))}</small>
          </li>
        ))}
      </ol>
    </>
  )
}

function SegmentPanel({ plan, i, change, snapshot, setSel, voice, busy, fixProp, findImages }: Props & { i: number }) {
  const s = plan.scenes[i]
  const propErr = usePropError(plan.style === '3d' ? s.prop : null)
  const set = (patch: Partial<SceneData>) => change({ ...plan, scenes: plan.scenes.map((x, j) => (j === i ? { ...x, ...patch } : x)) })
  const [capText, setCapText] = useState('')
  const [capErr, setCapErr] = useState('')
  useEffect(() => { setCapText((s.words ?? []).map((w) => w.text).join(' ')); setCapErr('') }, [s.words])

  function saveCaptions() {
    const toks = capText.trim().split(/\s+/).filter(Boolean)
    const words = s.words ?? []
    if (toks.length !== words.length) return setCapErr(`Keep ${words.length} words (you have ${toks.length}) so the timings still line up.`)
    snapshot()
    set({ words: words.map((w, k) => ({ ...w, text: toks[k] })) })
    setCapErr('')
  }

  return (
    <>
      <div className="seghead">
        <button className="link" onClick={() => setSel(null)}>← Overview</button>
        <h2>Segment {i + 1} <em>{s.kind}</em></h2>
        <small>{secs(sceneLen(s, plan.pace))}</small>
      </div>

      <label>Purpose<textarea rows={2} value={s.purpose ?? ''} placeholder="What this beat does for the viewer" onChange={(e) => set({ purpose: e.target.value })} /></label>

      <h3>On-screen script</h3>
      <label>Headline<input value={s.headline} onChange={(e) => set({ headline: e.target.value })} /></label>
      <label>Subline<input value={s.sub} onChange={(e) => set({ sub: e.target.value })} /></label>
      {s.kind === 'stat' && <label>Number<input value={s.value} onChange={(e) => set({ value: e.target.value })} /></label>}

      <h3>Timing · {secs(timing(s, plan.pace).frames)}</h3>
      <div className="imp-switch" role="group" aria-label="Importance">
        {([1, 2, 3] as Importance[]).map((lv) => (
          <button key={lv} className={(s.importance ?? 2) === lv ? 'on' : ''} onClick={() => { snapshot(); set({ importance: lv }) }}>{IMPORTANCE[lv].label}</button>
        ))}
      </div>
      <small className="tip">{(() => {
        const t = timing(s, plan.pace)
        return t.source === 'voice'
          ? `${secs(t.voice)} of voiceover + ${secs(t.hold)} hold for a ${IMPORTANCE[s.importance ?? 2].label.toLowerCase()} beat.`
          : `From ${t.words} words of on-screen script, ×${IMPORTANCE[s.importance ?? 2].scale} for importance. Generate the voice to time it to the narration.`
      })()}</small>

      <h3>Image</h3>
      {s.asset ? <img className="seg-img" src={s.asset} alt="" /> : <p className="tip">No image on this segment.</p>}
      <button onClick={() => findImages(`${plan.title} ${s.headline}`, i)} disabled={!!busy}>{busy === `find-${i}` ? 'Searching the web…' : 'Find images for this segment'}</button>

      <h3>Voiceover</h3>
      <textarea rows={4} value={s.voiceover ?? ''} placeholder="What the narrator says over this segment"
        onChange={(e) => set({ voiceover: e.target.value, audio: null, words: [] })} aria-label="Voiceover script" />
      <div className="row">
        <button onClick={() => voice(i)} disabled={!!busy || !s.voiceover?.trim()}>{busy === `voice-${i}` ? 'Voicing…' : s.audio ? 'Re-generate voice' : 'Generate voice'}</button>
        {s.audio && <audio src={s.audio.url} controls preload="none" />}
      </div>

      <h3>Captions</h3>
      {s.words?.length ? (
        <>
          <textarea rows={3} value={capText} onChange={(e) => setCapText(e.target.value)} onBlur={saveCaptions} aria-label="Caption words" />
          <small className={capErr ? 'err' : 'tip'}>{capErr || (s.captionSource === 'whisper' ? 'Fix any misheard words; timings come from Whisper.' : 'Timings from the voice engine (Whisper model not downloaded yet). Fix words freely.')}</small>
        </>
      ) : <p className="tip">Generate the voice to get word-timed captions.</p>}

      {plan.style === '3d' && (
        <>
          <h3>3D prop</h3>
          {s.prop ? (
            <>
              <p className="tip">{s.prop.name}{s.prop.credit ? ` · ${s.prop.credit}` : ''}</p>
              {propErr && <><p className="err">Couldn't build: {propErr}</p><button onClick={() => fixProp(i, propErr)} disabled={!!busy}>Fix with AI</button></>}
              <button className="link" onClick={() => { snapshot(); set({ prop: null }) }}>Remove prop</button>
            </>
          ) : <p className="tip">No prop. Ask in the prompt, e.g. "add a 3D jeepney here".</p>}
        </>
      )}
    </>
  )
}
