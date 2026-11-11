import { useEffect, useState } from 'react'
import type { Recipe } from './video/bench3d/recipe'
import { build, loadWasm } from './video/Stage3D'
import { FONTS, PALETTES, STYLES, resolveTheme } from './video/theme'
import { FPS, IMPORTANCE, MAX_LEN, MIN_LEN, OVERLAP, planDuration, sceneLen, timing, type Importance, type Plan, type SceneData, type Track } from './video/Video'

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
  fixLength: (i: number, seconds: number) => void // ask the AI to rewrite a segment's voiceover to fit a fixed length
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
const vis = (frames: number) => secs(frames - OVERLAP) // what the viewer sees of a segment, after the transition overlap

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
  const voiced = plan.scenes.filter((s) => s.audio).length
  return (
    <>
      <h2>Overview</h2>
      <label>Title<input value={plan.title} onChange={(e) => change({ ...plan, title: e.target.value })} /></label>

      <h3>Look</h3>
      {plan.styleOptions?.length ? (
        <div className="recs">
          <span className="rec-label">Style · AI pick first</span>
          <div className="chips-row">
            {plan.styleOptions.map((st, k) => (
              <button key={st} className={plan.style === st ? 'rec on' : 'rec'} onClick={() => { snapshot(); change({ ...plan, style: st }) }}>
                {k === 0 ? '★ ' : ''}{STYLES[st].label}
              </button>
            ))}
          </div>
          {plan.styleWhy && <small className="tip">{plan.styleWhy}</small>}
          {plan.style === '3d' && !plan.scenes.some((x) => x.prop) && <small className="tip">No 3D props yet: ask “add 3D props” in the prompt.</small>}
        </div>
      ) : null}
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

      <MusicPanel plan={plan} change={change} snapshot={snapshot} />

      <h3>Voice & captions</h3>
      <label>Narrator
        <select value={plan.voice ?? VOICES[0][0]} onChange={(e) => { snapshot(); change({ ...plan, voice: e.target.value }) }}>
          {VOICES.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
        </select>
      </label>
      <label className="check"><input type="checkbox" checked={plan.captions !== false} onChange={(e) => { snapshot(); change({ ...plan, captions: e.target.checked }) }} /> Show captions</label>
      <button onClick={() => voice(null)} disabled={!!busy}>{busy === 'voice-all' ? 'Voicing…' : `Voice all segments (${voiced}/${plan.scenes.length} done)`}</button>

      <h3>Segments · {secs(planDuration(plan))}</h3>
      <ol className="seglist">
        {plan.scenes.map((s, i) => (
          <li key={s.id} onClick={() => setSel(i)}>
            <em>{s.kind}</em><span>{s.purpose || s.headline}</span>
            <span className="bar"><i className={`imp${s.importance ?? 2}`} style={{ width: `${(sceneLen(s, plan.pace) / Math.max(...plan.scenes.map((x) => sceneLen(x, plan.pace)))) * 100}%` }} /></span>
            <small>{vis(sceneLen(s, plan.pace))}</small>
          </li>
        ))}
      </ol>
    </>
  )
}

// Music: the AI's pick and its runners-up as one-click recommendations, the full library, volume, or none.
function MusicPanel({ plan, change, snapshot }: Pick<Props, 'plan' | 'change' | 'snapshot'>) {
  const [library, setLibrary] = useState<Track[]>([])
  useEffect(() => { fetch('/api/music').then((r) => r.json()).then(setLibrary).catch(() => {}) }, [])
  const byId = Object.fromEntries(library.map((m) => [m.id, m]))
  const pick = (id: string) => { const m = byId[id]; if (m) { snapshot(); change({ ...plan, music: { ...m, volume: plan.music?.volume ?? 0.5 } }) } }
  const recs = (plan.musicOptions ?? []).filter((id) => byId[id])
  return (
    <>
      <h3>Music{plan.music ? ` · ${plan.music.title}` : ''}</h3>
      {recs.length > 0 && (
        <div className="recs">
          <span className="rec-label">Recommended · AI pick first</span>
          <div className="chips-row">
            {recs.map((id, k) => (
              <button key={id} className={plan.music?.id === id ? 'rec on' : 'rec'} onClick={() => pick(id)} title={byId[id].mood}>
                {k === 0 ? '★ ' : ''}{byId[id].title}
              </button>
            ))}
          </div>
          {plan.musicWhy && <small className="tip">{plan.musicWhy}</small>}
        </div>
      )}
      <div className="row">
        <label>Track
          <select value={plan.music?.id ?? ''} onChange={(e) => (e.target.value ? pick(e.target.value) : (snapshot(), change({ ...plan, music: null })))}>
            <option value="">No music</option>
            {library.map((m) => <option key={m.id} value={m.id}>{m.title} · {m.bpm} bpm</option>)}
          </select>
        </label>
        {plan.music && <label>Volume<input type="range" min={0} max={1} step={0.05} value={plan.music.volume ?? 0.5}
          onChange={(e) => change({ ...plan, music: { ...plan.music!, volume: Number(e.target.value) } })} /></label>}
      </div>
      {plan.music && <audio key={plan.music.url} src={plan.music.url} controls preload="none" className="music-preview" />}
      <small className="tip">Original loops made by Blockcut (royalty-free). Music dips automatically under the voiceover.</small>
    </>
  )
}

function SegmentPanel({ plan, i, change, snapshot, setSel, voice, busy, fixProp, findImages, fixLength }: Props & { i: number }) {
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
        <small>{vis(sceneLen(s, plan.pace))}</small>
      </div>

      <label>Purpose<textarea rows={2} value={s.purpose ?? ''} placeholder="What this beat does for the viewer" onChange={(e) => set({ purpose: e.target.value })} /></label>

      <h3>On-screen script</h3>
      <label>Headline<input value={s.headline} onChange={(e) => set({ headline: e.target.value })} /></label>
      <label>Subline<input value={s.sub} onChange={(e) => set({ sub: e.target.value })} /></label>
      {s.kind === 'stat' && <label>Number<input value={s.value} onChange={(e) => set({ value: e.target.value })} /></label>}

      <h3>Timing · {vis(timing(s, plan.pace).frames)}</h3>
      <div className="imp-switch" role="group" aria-label="Importance">
        {([1, 2, 3] as Importance[]).map((lv) => (
          <button key={lv} className={(s.importance ?? 2) === lv ? 'on' : ''} onClick={() => { snapshot(); set({ importance: lv }) }}>{IMPORTANCE[lv].label}</button>
        ))}
      </div>
      <label className="len-row">Exact length
        <div className="row">
          <input type="range" min={MIN_LEN} max={MAX_LEN} step={0.1} value={s.length ?? (sceneLen(s, plan.pace) - OVERLAP) / FPS}
            onChange={(e) => set({ length: Number(e.target.value) })} aria-label="Segment length in seconds" />
          <input type="number" min={MIN_LEN} max={MAX_LEN} step={0.1} className="secs-in" value={Number((s.length ?? (sceneLen(s, plan.pace) - OVERLAP) / FPS).toFixed(1))}
            onChange={(e) => e.target.value && set({ length: Math.min(MAX_LEN, Math.max(MIN_LEN, Number(e.target.value))) })} aria-label="Segment length, seconds" />
          {s.length ? <button className="link" onClick={() => { snapshot(); set({ length: null }) }}>Auto</button> : null}
        </div>
      </label>
      <small className="tip">{(() => {
        const t = timing(s, plan.pace)
        if (t.source === 'manual') return `Fixed at ${s.length?.toFixed(1)}s by you. Importance no longer changes it; press Auto to go back.`
        return t.source === 'voice'
          ? `${secs(t.voice)} of voiceover + ${secs(t.hold)} hold for a ${IMPORTANCE[s.importance ?? 2].label.toLowerCase()} beat. Drag the slider to set an exact length.`
          : `From ${t.words} words of on-screen script, ×${IMPORTANCE[s.importance ?? 2].scale} for importance. Drag the slider to set an exact length.`
      })()}</small>
      {timing(s, plan.pace).cutsVoice && s.length && (
        <div className="warn">
          The voiceover runs {secs(timing(s, plan.pace).voice)}, longer than {s.length.toFixed(1)}s, so it'll be cut off.
          <div className="row">
            <button onClick={() => fixLength(i, s.length!)} disabled={!!busy}>Shorten the line to fit</button>
            <button className="link" onClick={() => { snapshot(); set({ length: Math.ceil((timing(s, plan.pace).voice / FPS) * 10) / 10 + 0.3 }) }}>Use the voice's length</button>
          </div>
        </div>
      )}

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
