// Flyout panels opened from the left icon rail: Script (transcript), Style, Settings. The Assets panel lives in App
// because it shares upload/search state with the assistant. All panels edit the same Plan through change()/snapshot().
import { useEffect, useState, type ReactNode } from 'react'
import { FONTS, PALETTES, STYLES, resolveTheme, type Style } from './video/theme'
import { ASPECTS, CAPTION_LOOKS, EFFECTS, FPS, OVERLAP, ROLES, sceneLen, sceneStarts, TRANSITIONS, isEmpty, type Aspect, type Effect, type Plan, type Track, type Transition } from './video/Video'

export const VOICES = [
  ['en-US-AndrewNeural', 'Andrew · US'], ['en-US-AvaNeural', 'Ava · US'], ['en-GB-RyanNeural', 'Ryan · UK'],
  ['en-PH-JamesNeural', 'James · PH English'], ['en-PH-RosaNeural', 'Rosa · PH English'],
  ['fil-PH-AngeloNeural', 'Angelo · Filipino'], ['fil-PH-BlessicaNeural', 'Blessica · Filipino'],
] as const

type Edit = { plan: Plan; change: (p: Plan) => void; snapshot: () => void }
export type Tile = { type: 'transition'; name: Transition } | { type: 'effect'; name: Effect }

export const stamp = (sec: number) => `${Math.floor(sec / 60)}:${(sec % 60).toFixed(1).padStart(4, '0')}`
// Start/end of each segment as the viewer sees it: segment i runs from its start to the next segment's start.
export const spans = (plan: Plan) => {
  const starts = sceneStarts(plan)
  return plan.scenes.map((s, i) => {
    const start = starts[i] / FPS
    return { start, end: start + (sceneLen(s, plan.pace) - OVERLAP) / FPS }
  })
}

export function Flyout({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  return (
    <section className={`flyout${wide ? ' wide' : ''}`} aria-label={title}>
      <header><b>{title}</b><button className="x" onClick={onClose} aria-label={`Close ${title}`}>×</button></header>
      <div className="flyout-body">{children}</div>
    </section>
  )
}

// The whole script in order. It edits the same scene fields as the inspector, so the two can't drift apart.
export function ScriptPanel({ plan, change, sel, onSelect }: Edit & { sel: number | null; onSelect: (i: number) => void }) {
  const times = spans(plan)
  const set = (i: number, patch: Partial<Plan['scenes'][number]>) =>
    change({ ...plan, scenes: plan.scenes.map((x, j) => (j === i ? { ...x, ...patch } : x)) })
  return (
    <ol className="transcript">
      {plan.scenes.map((s, i) => (
        <li key={s.id} className={`${sel === i ? 'on' : ''} ${isEmpty(s) ? 'empty' : ''}`} onClick={() => onSelect(i)}>
          <div className="t-head">
            <span className="t-num">{String(i + 1).padStart(2, '0')}</span>
            <span className="t-time">{stamp(times[i].start)}–{stamp(times[i].end)}</span>
            <em>{s.title || (s.role ? ROLES[s.role] : s.kind)}</em>
          </div>
          <textarea rows={3} value={s.voiceover ?? ''} placeholder={isEmpty(s) ? 'Empty segment: write narration, or ask the assistant to fill it' : 'Narration'}
            onClick={(e) => e.stopPropagation()} onFocus={() => onSelect(i)}
            onChange={(e) => set(i, { voiceover: e.target.value, audio: null, words: [] })} aria-label={`Narration for segment ${i + 1}`} />
          <small className="tip">On screen: {s.value && <b>{s.value} </b>}{s.headline || '—'}</small>
        </li>
      ))}
    </ol>
  )
}

export type SavedStyle = { id: string; label: string; description?: string; video_type?: string; custom?: boolean
  editing?: { pace?: string; captions?: string }; visual?: { style?: string; palette?: string }
  measured?: { cuts_per_minute?: number; median_shot_seconds?: number }; source?: { url?: string; title?: string; channel?: string } }

// YouTube link -> reusable style (server job); used on the start screen and in the Style panel.
export function StyleFromUrl({ onDone, locked }: { onDone?: (s: SavedStyle) => void; locked?: () => void }) { // locked: demo mode, no backend
  const [refUrl, setRefUrl] = useState('')
  const [refJob, setRefJob] = useState<{ id?: string; status?: string; stage?: string; progress?: number; error?: string; style?: SavedStyle } | null>(null)
  const running = ['queued', 'running'].includes(refJob?.status ?? '')
  useEffect(() => {
    if (!refJob?.id || !running) return
    const timer = window.setInterval(async () => {
      try {
        const j = await (await fetch(`/api/styles/jobs/${refJob.id}`)).json()
        setRefJob(j)
        if (j.status === 'done') { window.dispatchEvent(new Event('blockcut-styles-updated')); onDone?.(j.style) }
      } catch { /* next poll can recover */ }
    }, 1200)
    return () => window.clearInterval(timer)
  }, [refJob?.id, running])
  const start = async () => {
    setRefJob({ status: 'queued', stage: 'starting', progress: 0 })
    try {
      const r = await fetch('/api/styles/from-url', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: refUrl }) })
      const j = await r.json()
      if (!r.ok) throw new Error(j.error || 'Could not start style extraction')
      setRefJob(j)
    } catch (e) { setRefJob({ status: 'error', error: e instanceof Error ? e.message : String(e) }) }
  }
  return (
    <div className="style-from-url">
      <form className="row" onSubmit={(e) => { e.preventDefault(); if (locked) locked(); else if (refUrl && !running) start() }}>
        <input type="url" value={refUrl} onChange={(e) => setRefUrl(e.target.value)} placeholder="YouTube link (a video under 3 minutes)" aria-label="YouTube video link" />
        <button type="submit" disabled={!refUrl || running}>{running ? 'Studying…' : 'Create style'}</button>
      </form>
      {running && <div className="style-progress"><i style={{ width: `${refJob?.progress ?? 5}%` }} /><small>{refJob?.stage}</small></div>}
      {refJob?.error && <small role="alert" className="tip">{refJob.error}</small>}
      {refJob?.status === 'done' && refJob.style && <small className="tip">Saved “{refJob.style.label}”. It is in the format menu under “Your styles”.</small>}
    </div>
  )
}

// Same rule as content_styles.plan_settings: these caption notes mean "no word captions".
const capsOff = (c?: string) => /^\s*(none|off|minimal|no\b)|\bno (full )?(burned.in )?(subtitles|captions)/i.test(c ?? '')

function StyleCard({ s, current, busy, onRestyle, onDelete }: { s: SavedStyle; current: boolean; busy: boolean; onRestyle: () => void; onDelete: () => void }) {
  const m = s.measured
  return (
    <article className={`style-card${current ? ' on' : ''}`}>
      <header><b>{s.label}</b>{current && <span className="pill">this video</span>}</header>
      <small>{s.video_type}</small>
      <div className="style-facts">
        {m?.median_shot_seconds ? <span title="Measured from the reference">{m.cuts_per_minute} cuts/min · {m.median_shot_seconds}s shots</span> : null}
        <span>{s.editing?.pace === 'documentary' ? 'Calm pace' : 'Punchy pace'}</span>
        <span>{capsOff(s.editing?.captions) ? 'No captions' : 'Captions'}</span>
        {s.visual?.palette && <span>{s.visual.style ?? ''} · {s.visual.palette}</span>}
      </div>
      {s.source?.url && <a href={s.source.url} target="_blank" rel="noreferrer">From: {s.source.title}</a>}
      <div className="row">
        <button onClick={onRestyle} disabled={busy || current}>{current ? 'In use' : 'Restyle this video'}</button>
        <button className="link" onClick={onDelete} disabled={busy}>Delete</button>
      </div>
    </article>
  )
}

export function StylePanel({ plan, change, snapshot, tileProps, onRestyle, busy }: Edit & { tileProps: (t: Tile) => object; onRestyle: (s: SavedStyle) => void; busy: boolean }) {
  const [mine, setMine] = useState<SavedStyle[]>([])
  useEffect(() => {
    const load = () => fetch('/api/styles').then((r) => r.json()).then((all: SavedStyle[]) => setMine(all.filter((x) => x.custom))).catch(() => {})
    load()
    window.addEventListener('blockcut-styles-updated', load)
    return () => window.removeEventListener('blockcut-styles-updated', load)
  }, [])
  const remove = async (s: SavedStyle) => {
    if (!window.confirm(`Delete the style “${s.label}”? Videos already made with it keep their script.`)) return
    await fetch('/api/styles/delete', { method: 'POST', body: JSON.stringify({ id: s.id }) })
    window.dispatchEvent(new Event('blockcut-styles-updated'))
  }
  const t = resolveTheme(plan.style, plan.theme)
  const theme = (k: string, v: unknown) => { snapshot(); change({ ...plan, theme: { ...plan.theme, [k]: v } }) }
  const cap = (k: string, v: string) => { snapshot(); change({ ...plan, captionStyle: { ...plan.captionStyle, [k]: v } }) }
  return (
    <>
      <h3>Your styles</h3>
      <small className="tip">Styles learned from YouTube videos: their structure, writing and cut rhythm. Restyle rewrites this video in one.</small>
      {mine.map((x) => <StyleCard key={x.id} s={x} current={plan.contentStyle === x.id} busy={busy} onRestyle={() => onRestyle(x)} onDelete={() => remove(x)} />)}
      <StyleFromUrl />
      <label>Visual style
        <select value={plan.style} onChange={(e) => { snapshot(); change({ ...plan, style: e.target.value as Style }) }}>
          {(Object.keys(STYLES) as Style[]).map((k) => <option key={k} value={k}>{STYLES[k].label}</option>)}
        </select>
      </label>
      {plan.styleOptions?.length ? (
        <div className="recs">
          <span className="rec-label">Recommended · AI pick first</span>
          <div className="chips-row">
            {plan.styleOptions.map((st, k) => (
              <button key={st} className={plan.style === st ? 'rec on' : 'rec'} onClick={() => { snapshot(); change({ ...plan, style: st }) }}>
                {k === 0 ? '★ ' : ''}{STYLES[st].label}
              </button>
            ))}
          </div>
          {plan.styleWhy && <small className="tip">{plan.styleWhy}</small>}
          {plan.style === '3d' && !plan.scenes.some((x) => x.prop) && <small className="tip">No 3D props yet: ask the assistant to “add 3D props”.</small>}
        </div>
      ) : null}

      <h3>Colour</h3>
      <div className="swatches">
        {Object.entries(PALETTES).map(([k, pal]) => (
          <button key={k} className={(plan.theme?.palette ?? STYLES[plan.style].palette) === k ? 'sw on' : 'sw'} title={pal.label} aria-label={pal.label} onClick={() => theme('palette', k)}>
            {pal.bg.slice(0, 4).map((c, j) => <i key={j} style={{ background: c }} />)}
          </button>
        ))}
      </div>
      <div className="row">
        <label>Accent<input type="color" value={t.accent} onChange={(e) => theme('accent', e.target.value)} /></label>
        <label>Grain<input type="range" min={0} max={0.4} step={0.02} value={t.grain} onChange={(e) => theme('grain', Number(e.target.value))} /></label>
      </div>

      <h3>Typography</h3>
      <div className="row">
        <label>Headings<select value={t.display} onChange={(e) => theme('display', e.target.value)}>{FONTS.map((f) => <option key={f}>{f}</option>)}</select></label>
        <label>Body<select value={t.body} onChange={(e) => theme('body', e.target.value)}>{FONTS.map((f) => <option key={f}>{f}</option>)}</select></label>
      </div>

      <h3>Editing</h3>
      <label>Pace
        <select value={plan.pace} onChange={(e) => { snapshot(); change({ ...plan, pace: e.target.value as Plan['pace'] }) }}>
          <option value="punchy">Punchy</option><option value="documentary">Documentary</option>
        </select>
      </label>
      <h3>Captions</h3>
      <label className="check"><input type="checkbox" checked={plan.captions !== false} onChange={(e) => { snapshot(); change({ ...plan, captions: e.target.checked }) }} /> Word-by-word captions</label>
      {plan.captions !== false && (
        <div className="row">
          <label>Position
            <select value={plan.captionStyle?.position ?? 'bottom'} onChange={(e) => cap('position', e.target.value)}>
              <option value="bottom">Bottom</option><option value="middle">Middle</option><option value="top">Top</option>
            </select>
          </label>
          <label>Size
            <select value={plan.captionStyle?.size ?? 'm'} onChange={(e) => cap('size', e.target.value)}>
              <option value="s">Small</option><option value="m">Medium</option><option value="l">Large</option>
            </select>
          </label>
          <label>Look
            <select value={plan.captionStyle?.look ?? 'box'} onChange={(e) => cap('look', e.target.value)}>
              {Object.entries(CAPTION_LOOKS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
        </div>
      )}
      <small className="tip">Captions appear once segments are voiced (Settings → Voice all segments).</small>
      <h3>Transitions & effects</h3>
      <span className="rec-label">Transitions · drag onto a segment</span>
      <div className="grid">
        {(Object.keys(TRANSITIONS) as Transition[]).map((name) => (
          <button key={name} className="fx" {...tileProps({ type: 'transition', name })}><div className={`pv pv-${name}`}><span>Aa</span></div>{TRANSITIONS[name]}</button>
        ))}
      </div>
      <span className="rec-label">Effects · drag onto a segment</span>
      <div className="grid">
        {(Object.keys(EFFECTS) as Effect[]).map((name) => (
          <button key={name} className="fx" {...tileProps({ type: 'effect', name })}><div className={`pv pv-${name}`}><span>Aa</span></div>{EFFECTS[name]}</button>
        ))}
      </div>
      {plan.theme && <button className="link" onClick={() => { snapshot(); change({ ...plan, theme: undefined }) }}>Reset colours and fonts to style defaults</button>}
    </>
  )
}

export function SettingsPanel({ plan, change, snapshot, voice, busy, onExport, onRender, renderUrl }: Edit & { voice: (i: number | null) => void; busy: string; onExport: () => void; onRender: () => void; renderUrl: string }) {
  const voiced = plan.scenes.filter((s) => s.audio).length
  const [qwenVoices, setQwenVoices] = useState<string[]>([])
  useEffect(() => { fetch('/api/voices').then(r => r.ok ? r.json() : null).then(d => setQwenVoices(d?.voices ?? [])).catch(() => {}) }, [])
  return (
    <>
      <label>Title<input value={plan.title} onChange={(e) => change({ ...plan, title: e.target.value })} /></label>
      <label>Format
        <select value={plan.aspect ?? '16:9'} onChange={(e) => { snapshot(); change({ ...plan, aspect: e.target.value as Aspect }) }}>
          {(Object.keys(ASPECTS) as Aspect[]).map((k) => <option key={k} value={k}>{ASPECTS[k].label}</option>)}
        </select>
      </label>

      <h3>Voiceover</h3>
      <label>Narrator
        <select value={plan.voice ?? VOICES[0][0]} onChange={(e) => { snapshot(); change({ ...plan, voice: e.target.value }) }}>
          {[...VOICES.map(([id, name]) => [id, name] as const), ...qwenVoices.map(id => [id, `${id.split(':')[1]} · natural (Qwen)`] as const)].map(([id, name]) => <option key={id} value={id}>{name}</option>)}
        </select>
      </label>
      <button onClick={() => voice(null)} disabled={!!busy}>{busy === 'voice-all' ? 'Voicing…' : `Voice all segments (${voiced}/${plan.scenes.length} done)`}</button>
      <label>Talking speed · {plan.voiceRate ?? 0}%
        <input type="range" min={-20} max={40} step={5} value={plan.voiceRate ?? 0}
          onPointerDown={snapshot} onKeyDown={(e) => { if (e.key.startsWith('Arrow')) snapshot() }}
          onChange={(e) => change({ ...plan, voiceRate: Number(e.target.value) })} />
      </label>
      <small className="tip">Set the pace, then regenerate voiceover to apply it to the audio and captions.</small>

      <MusicPanel plan={plan} change={change} snapshot={snapshot} />

      <h3>Project</h3>
      <button onClick={onRender} disabled={!!busy}>{busy === 'render' ? 'Rendering MP4…' : 'Render MP4'}</button>
      {renderUrl && <a className="button" href={renderUrl} download>Download finished video</a>}
      <button className="ghost" onClick={onExport}>Download project file (.json)</button>
      <small className="tip">Your project saves in this browser automatically.</small>
    </>
  )
}

// Music: the AI's pick and its runners-up as one-click recommendations, the full library, volume, or none.
function MusicPanel({ plan, change, snapshot }: Edit) {
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
              <button key={id} className={plan.music?.id === id ? 'rec on' : 'rec'} onClick={() => pick(id)} title={byId[id].mood}>{k === 0 ? '★ ' : ''}{byId[id].title}</button>
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
      <small className="tip">Original loops made by ShortCut (royalty-free). Music dips under the voiceover.</small>
    </>
  )
}
