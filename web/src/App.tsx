import { Player, type PlayerRef } from '@remotion/player'
import { useEffect, useRef, useState } from 'react'
import { Canvas } from './Canvas'
import { Inspector } from './Inspector'
import { Flyout, ScriptPanel, SettingsPanel, StylePanel, type Tile } from './Panels'
import { STYLES, type Style } from './video/theme'
import { ASPECTS, dims, FPS, isEmpty, Main, planDuration, ROLES, sceneStarts, type Aspect, type Plan, type SceneData } from './video/Video'
import './App.css'
import './studio.css'

type Asset = { url: string; name: string; source?: string }
type Item = Tile | { type: 'asset'; url: string; name: string }
type Msg = { who: 'you' | 'ai'; text: string; scope: string }
type PanelId = 'assets' | 'script' | 'style' | 'settings'
// Real generation stages (spec §4A): the bar advances when a stage actually finishes, not on a timer.
type Gen = { stages: string[]; at: number }

async function api(path: string, body?: unknown) {
  const r = await fetch(path, body === undefined ? undefined : { method: 'POST', body: JSON.stringify(body) })
  const text = await r.text()
  if (!text) throw new Error('API server not running — start it with: .venv/Scripts/python server.py')
  const j = JSON.parse(text)
  if (!r.ok) throw new Error(j.error)
  return j
}

const readDataUrl = (f: File) => new Promise<string>((ok, fail) => {
  const r = new FileReader()
  r.onload = () => ok(r.result as string)
  r.onerror = fail
  r.readAsDataURL(f)
})
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))

// The project survives refreshes: plan + assistant history live in this browser (spec acceptance: assets stay accessible).
const SAVE_KEY = 'blockcut.project.v1'
const saved = (() => { try { return JSON.parse(localStorage.getItem(SAVE_KEY) ?? 'null') as { plan: Plan | null; log: Msg[] } | null } catch { return null } })()

const ICONS: Record<PanelId, { label: string; path: string }> = {
  assets: { label: 'Asset Library', path: 'M4 5h16v14H4zM4 15l5-5 4 4 3-3 4 4M15 9.5a1.5 1.5 0 1 0 0-.01' },
  script: { label: 'Transcript / Script', path: 'M6 3h9l3 3v15H6zM9 9h6M9 13h6M9 17h4' },
  style: { label: 'Video Style', path: 'M12 3a9 9 0 1 0 0 18c1 0 1.5-.8 1.5-1.6 0-1.2-1-1.4-1-2.4 0-.8.7-1.5 1.5-1.5H17a4 4 0 0 0 4-4c0-4.7-4-8.5-9-8.5zM7.5 11a1 1 0 1 0 0-.01M10 7.5a1 1 0 1 0 0-.01M14.5 7.5a1 1 0 1 0 0-.01' },
  settings: { label: 'Project Settings', path: 'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM19.4 13.5l1.6 1.2-2 3.4-1.9-.7a7 7 0 0 1-2 1.2L14.8 21h-4l-.3-2.4a7 7 0 0 1-2-1.2l-1.9.7-2-3.4 1.6-1.2a7 7 0 0 1 0-2.4L4.6 9.9l2-3.4 1.9.7a7 7 0 0 1 2-1.2L10.8 3h4l.3 2.4a7 7 0 0 1 2 1.2l1.9-.7 2 3.4-1.6 1.2a7 7 0 0 1 0 2.4z' },
}

export default function App() {
  const [plan, setPlanRaw] = useState<Plan | null>(saved?.plan ?? null)
  const [history, setHistory] = useState<Plan[]>([])
  const [sel, setSel] = useState<number | null>(null)
  const [inspOpen, setInspOpen] = useState(false)
  const [panel, setPanel] = useState<PanelId | null>(null)
  const [assistOpen, setAssistOpen] = useState(false)
  const [log, setLog] = useState<Msg[]>(saved?.log ?? [])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState('') // '' | 'ai' | 'gen' | 'voice-all' | 'voice-<i>' | 'find' | 'find-<i>'
  const [gen, setGen] = useState<Gen | null>(null)
  const [leaving, setLeaving] = useState(false) // hero prompt shrinking into the assistant icon
  const [reveal, setReveal] = useState(Infinity) // cards shown so far during the reveal
  const [previewIn, setPreviewIn] = useState(!!saved?.plan)
  const [toast, setToast] = useState<{ text: string; undo: boolean } | null>(null)
  const [style, setStyle] = useState<Style | 'auto'>('auto')
  const [aspect, setAspect] = useState<Aspect>('9:16')
  const [assets, setAssets] = useState<Asset[]>([])
  const [scrapeUrl, setScrapeUrl] = useState('')
  const [findQuery, setFindQuery] = useState('')
  const [autoImages, setAutoImages] = useState(true)
  const [assetMsg, setAssetMsg] = useState('')
  const player = useRef<PlayerRef>(null)
  const planRef = useRef(plan)
  planRef.current = plan

  useEffect(() => { api('/api/assets').then(setAssets).catch(() => {}) }, [])
  useEffect(() => { // autosave (skipped mid-reveal so a refresh can't save a half-shown storyboard)
    if (gen) return
    try { localStorage.setItem(SAVE_KEY, JSON.stringify({ plan, log: log.slice(-60) })) } catch { /* storage full or blocked */ }
  }, [plan, log, gen])

  // History: discrete actions (setPlan) always get an undo step; live edits (change) start a new step after a
  // 1 s pause, so a burst of typing in one field undoes in one go.
  const lastEdit = useRef(0)
  const snapshot = () => { const p = planRef.current; if (p) setHistory((h) => [...h.slice(-40), p]); lastEdit.current = Date.now() }
  const change = (p: Plan) => {
    if (Date.now() - lastEdit.current > 1000) snapshot()
    else lastEdit.current = Date.now()
    setPlanRaw(p)
  }
  const setPlan = (p: Plan) => { snapshot(); setPlanRaw(p) }
  const undo = () => {
    const prev = history.at(-1)
    if (!prev) return
    setHistory((h) => h.slice(0, -1))
    setPlanRaw(prev)
    setSel((s) => (s !== null && s >= prev.scenes.length ? null : s))
    setToast(null)
  }
  const patchScene = (i: number, fn: (s: SceneData) => SceneData) =>
    plan && setPlan({ ...plan, scenes: plan.scenes.map((s, j) => (j === i ? fn(s) : s)) })

  const select = (i: number) => { setSel(i); setInspOpen(true) }
  useEffect(() => {
    if (plan && sel !== null && sel < plan.scenes.length) player.current?.seekTo(sceneStarts(plan)[sel] + 8)
  }, [sel]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!toast) return; const t = setTimeout(() => setToast(null), 6000); return () => clearTimeout(t) }, [toast])

  function apply(i: number, it: Item) {
    if (it.type === 'transition') patchScene(i, (s) => ({ ...s, transition: it.name }))
    if (it.type === 'effect') patchScene(i, (s) => (s.effects.includes(it.name) ? s : { ...s, effects: [...s.effects, it.name] }))
    if (it.type === 'asset') patchScene(i, (s) => ({ ...s, asset: it.url }))
    select(i)
  }

  function reorder(from: number, to: number) {
    if (!plan || from === to) return
    const scenes = [...plan.scenes]
    const [moved] = scenes.splice(from, 1)
    scenes.splice(to, 0, moved)
    setPlan({ ...plan, scenes })
    select(to)
  }

  // Segment management (spec §9): insert an empty segment exactly here; delete with an undo toast.
  function insert(at: number) {
    if (!plan) return
    const blank: SceneData = { id: Math.random().toString(36).slice(2, 10), kind: 'fact', role: 'narration', title: '', headline: '', sub: '', value: '',
      transition: 'cut', effects: [], importance: 2, purpose: '', voiceover: '', audio: null, words: [] }
    setPlan({ ...plan, scenes: [...plan.scenes.slice(0, at), blank, ...plan.scenes.slice(at)] })
    select(at)
  }
  function remove(i: number) {
    if (!plan) return
    const gone = plan.scenes[i]
    setPlan({ ...plan, scenes: plan.scenes.filter((_, j) => j !== i) })
    setSel((s) => (s === null ? null : s === i ? (plan.scenes.length > 1 ? Math.min(i, plan.scenes.length - 2) : null) : s > i ? s - 1 : s))
    setToast({ text: `Deleted segment ${i + 1}${gone.title ? ` · ${gone.title}` : ''}`, undo: true })
  }

  const scopeOf = (i: number | null) => (i !== null && plan?.scenes[i] ? `Segment ${i + 1} · ${plan.scenes[i].title || (plan.scenes[i].role ? ROLES[plan.scenes[i].role!] : plan.scenes[i].kind)}` : plan ? 'Whole video' : 'New video')
  const scope = scopeOf(sel)
  const say = (who: Msg['who'], text: string, s = scope) => setLog((l) => [...l, { who, text, scope: s }])
  const errText = (e: unknown) => `⚠ ${e instanceof Error ? e.message : e}`

  // First prompt: hero shrinks into the assistant, then images → script → storyboard reveal → preview, each a real step.
  async function generate(text: string) {
    const stages = [...(autoImages ? ['Finding images'] : []), 'Researching & writing the script', 'Building the storyboard', 'Preparing the preview']
    setLeaving(true)
    setBusy('gen')
    setGen({ stages, at: 0 })
    say('you', text, 'New video')
    await wait(450) // let the hero finish its ease into the corner
    setLeaving(false)
    let at = 0
    try {
      let bucket = assets
      if (autoImages) {
        try {
          const found: Asset[] = await api('/api/assets/find', { query: text, limit: 6 })
          bucket = [...assets, ...found]
          setAssets(bucket)
          say('ai', `Found ${found.length} images for “${text}” (ScrapeGraphAI web search).`, 'New video')
        } catch (e) {
          say('ai', `${errText(e)} · carrying on without new images.`, 'New video')
        }
        setGen({ stages, at: ++at })
      }
      const p: Plan & { note?: string } = await api('/api/plan', { topic: text, style, aspect, pace: 'punchy', assets: bucket })
      setGen({ stages, at: ++at })
      setReveal(0)
      setPreviewIn(false)
      setHistory([])
      setPlanRaw(p)
      for (let k = 1; k <= p.scenes.length; k++) { await wait(260); setReveal(k) } // cards populate one by one
      setGen({ stages, at: ++at })
      await wait(150)
      setPreviewIn(true) // preview slides in once the storyboard is complete
      await wait(500)
      say('ai', p.note ?? `Made ${p.scenes.length} segments.`, 'New video')
    } catch (e) {
      say('ai', errText(e), 'New video')
      setAssistOpen(true)
    } finally {
      setReveal(Infinity)
      setGen(null)
      setBusy('')
    }
  }

  async function prompt(text: string, index = sel) {
    if (!text || busy) return
    if (!plan) return generate(text)
    const s = scopeOf(index)
    setBusy('ai')
    say('you', text, s)
    try {
      const r = await api('/api/edit', { plan, index, instruction: text, assets })
      setPlan(r.plan)
      say('ai', r.note, s)
    } catch (e) {
      say('ai', errText(e), s)
    } finally {
      setBusy('')
    }
  }
  const send = () => { const t = input.trim(); if (t && !busy) { setInput(''); prompt(t) } }

  async function voice(index: number | null) {
    if (!plan || busy) return
    setBusy(index === null ? 'voice-all' : `voice-${index}`)
    try {
      const r = await api('/api/voice', { plan, index })
      setPlan(r.plan)
    } catch (e) {
      say('ai', errText(e), index === null ? 'Voiceover' : `Segment ${index + 1} voice`)
    } finally {
      setBusy('')
    }
  }

  async function addFiles(files: FileList | null) {
    if (!files?.length) return
    setAssetMsg('Uploading…')
    try {
      const added: Asset[] = []
      for (const f of Array.from(files)) added.push(await api('/api/assets/upload', { name: f.name, data: await readDataUrl(f) }))
      setAssets((a) => [...a, ...added])
      setAssetMsg(`Added ${added.length}`)
    } catch (e) {
      setAssetMsg(errText(e))
    }
  }

  async function scrape() {
    if (!scrapeUrl.trim()) return
    setAssetMsg('Scraping images…')
    try {
      const added: Asset[] = await api('/api/assets/scrape', { url: scrapeUrl.trim() })
      setAssets((a) => [...a, ...added])
      setAssetMsg(`Added ${added.length} from page`)
      setScrapeUrl('')
    } catch (e) {
      setAssetMsg(errText(e))
    }
  }

  // ScrapeGraphAI web search -> relevant images in the bucket; with assignTo, the best one goes on that segment.
  async function findImages(query: string, assignTo: number | null = null) {
    if (!query.trim() || busy) return
    setBusy(assignTo === null ? 'find' : `find-${assignTo}`)
    setAssetMsg(`Searching the web for “${query}”…`)
    try {
      const found: Asset[] = await api('/api/assets/find', { query, limit: assignTo === null ? 8 : 4 })
      setAssets((a) => [...a, ...found])
      setAssetMsg(`Added ${found.length} images`)
      if (assignTo !== null && found[0]) patchScene(assignTo, (s) => ({ ...s, asset: found[0].url }))
    } catch (e) {
      setAssetMsg(errText(e))
    } finally {
      setBusy('')
    }
  }

  async function removeAsset(url: string) {
    await api('/api/assets/delete', { url }).catch(() => {})
    setAssets((a) => a.filter((x) => x.url !== url))
  }

  function download() {
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([JSON.stringify(plan, null, 2)], { type: 'application/json' }))
    a.download = 'blockcut-project.json'
    a.click()
  }

  function newProject() {
    if (plan && !confirm('Start a new video? The current one will be replaced (download it first from Settings if you want to keep it).')) return
    setPlanRaw(null); setHistory([]); setSel(null); setInspOpen(false); setPanel(null); setLog([]); setPreviewIn(false)
  }

  const tileProps = (it: Item) => ({
    draggable: true,
    onDragStart: (e: React.DragEvent) => e.dataTransfer.setData('text/plain', JSON.stringify(it)),
    onClick: () => sel !== null && apply(sel, it),
    title: sel !== null ? `Apply to segment ${sel + 1}` : 'Drag onto a segment',
  })

  const started = !!plan || !!gen
  const selEmpty = plan && sel !== null && plan.scenes[sel] ? isEmpty(plan.scenes[sel]) : false
  const busyLabel = gen ? gen.stages[Math.min(gen.at, gen.stages.length - 1)]
    : busy === 'ai' ? 'Applying your edit…' : busy === 'voice-all' ? 'Voicing all segments…' : busy.startsWith('voice-') ? 'Voicing the segment…'
      : busy.startsWith('find') ? 'Searching the web for images…' : ''
  const curAspect = plan?.aspect ?? aspect
  const { w, h } = ASPECTS[curAspect]

  const assetsPanel = (
    <>
      <div className="asset-add">
        <form onSubmit={(e) => { e.preventDefault(); findImages(findQuery || plan?.title || '') }}>
          <input value={findQuery} onChange={(e) => setFindQuery(e.target.value)} placeholder={plan ? `Find images: ${plan.title}` : 'Find images for a topic'} aria-label="Topic to find images for" />
          <button type="submit" disabled={!!busy || !(findQuery || plan?.title)}>{busy === 'find' ? 'Searching…' : 'Find'}</button>
        </form>
        <label className="upload">Upload images<input type="file" accept="image/png,image/jpeg,image/webp,image/gif" multiple onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} hidden /></label>
        <form onSubmit={(e) => { e.preventDefault(); scrape() }}>
          <input value={scrapeUrl} onChange={(e) => setScrapeUrl(e.target.value)} placeholder="Paste a page URL to grab its images" aria-label="Page URL to scrape images from" />
          <button type="submit" disabled={!scrapeUrl.trim()}>Grab</button>
        </form>
      </div>
      <div className="grid assets" onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files) }}>
        {assets.map((a) => (
          <div key={a.url} className="fx asset" {...tileProps({ type: 'asset', url: a.url, name: a.name })}>
            <img src={a.url} alt={a.name} title={a.source ? `From ${a.source}` : a.name} />
            <span>{a.name}</span>
            <button className="x del" onClick={(e) => { e.stopPropagation(); removeAsset(a.url) }} aria-label={`Delete ${a.name}`}>×</button>
          </div>
        ))}
        {!assets.length && <p className="tip span">Find images for a topic, drop or upload your own, or grab them from a page. Found images are other people's work: check you can use them.</p>}
      </div>
      {assetMsg && <p className="tip">{assetMsg}</p>}
      <p className="tip">Drag an image onto a storyboard card or the inspector's Media box. The same image can go on several segments. Video upload is coming with the footage workflow.</p>
    </>
  )

  return (
    <div className={`studio ${started ? 'started' : ''}`}>
      {started && (
        <nav className="rail" aria-label="Panels">
          <div className="rail-brand" title="Blockcut">B</div>
          {(Object.keys(ICONS) as PanelId[]).map((id, k) => (
            <button key={id} className={`rail-btn ${panel === id ? 'on' : ''}`} style={{ animationDelay: `${k * 70}ms` }}
              data-label={ICONS[id].label} aria-label={ICONS[id].label} onClick={() => setPanel(panel === id ? null : id)}>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS[id].path} /></svg>
            </button>
          ))}
        </nav>
      )}

      {started && panel && (
        <Flyout title={ICONS[panel].label} onClose={() => setPanel(null)}>
          {panel === 'assets' && assetsPanel}
          {panel === 'script' && plan && <ScriptPanel plan={plan} change={change} snapshot={snapshot} sel={sel} onSelect={select} />}
          {panel === 'style' && plan && <StylePanel plan={plan} change={change} snapshot={snapshot} tileProps={tileProps} />}
          {panel === 'settings' && plan && <SettingsPanel plan={plan} change={change} snapshot={snapshot} voice={voice} busy={busy} onExport={download} />}
          {!plan && panel !== 'assets' && <p className="tip">Available once the storyboard is ready.</p>}
        </Flyout>
      )}

      <main>
        {started && (
          <header>
            <b>{plan?.title ?? 'Generating…'}</b>
            <button className="ghost" onClick={undo} disabled={!history.length}>Undo</button>
            <button className="ghost" onClick={newProject} disabled={!!gen}>New video</button>
          </header>
        )}

        {(!started || leaving) && (
          <div className={`hero ${leaving ? 'leaving' : ''}`}>
            <h1>What video should we make?</h1>
            <p className="tip">Any topic: food, history, games, explainers. Blockcut researches it, writes the script, builds the storyboard and edits it.</p>
            <textarea value={input} onChange={(e) => setInput(e.target.value)} rows={3} autoFocus
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
              placeholder="e.g. A 45-second explainer on why Filipinos love ube" aria-label="Describe your video" />
            <div className="hero-opts">
              <select value={style} onChange={(e) => setStyle(e.target.value as Style | 'auto')} aria-label="Visual style">
                <option value="auto">Auto style (AI picks)</option>
                {(Object.keys(STYLES) as Style[]).map((k) => <option key={k} value={k}>{STYLES[k].label}</option>)}
              </select>
              <select value={aspect} onChange={(e) => setAspect(e.target.value as Aspect)} aria-label="Format">
                {(Object.keys(ASPECTS) as Aspect[]).map((k) => <option key={k} value={k}>{ASPECTS[k].label}</option>)}
              </select>
              <label className="check-row"><input type="checkbox" checked={autoImages} onChange={(e) => setAutoImages(e.target.checked)} /> Find topic images</label>
              <button onClick={send} disabled={!!busy || !input.trim()}>Generate ✦</button>
            </div>
          </div>
        )}

        {plan && (
          <>
            <div className={`stage ${previewIn ? 'in' : ''}`} style={{ aspectRatio: `${w} / ${h}` }}>
              {previewIn && <Player ref={player} component={Main} inputProps={plan} durationInFrames={planDuration(plan)} fps={FPS}
                compositionWidth={dims(plan).w} compositionHeight={dims(plan).h} style={{ width: '100%', height: '100%' }} controls loop />}
            </div>
            <Canvas
              plan={plan}
              sel={sel}
              reveal={reveal}
              onToggle={select}
              onClear={() => {}}
              onReorder={reorder}
              onDropItem={(i, json) => { try { apply(i, JSON.parse(json)) } catch { /* not one of our tiles */ } }}
              onRemoveEffect={(i, e) => patchScene(i, (s) => ({ ...s, effects: s.effects.filter((x) => x !== e) }))}
              onRemoveAsset={(i) => patchScene(i, (s) => ({ ...s, asset: '' }))}
              onImportance={(i, lv) => patchScene(i, (s) => ({ ...s, importance: lv, length: null }))}
              onInsert={insert}
              onDelete={remove}
            />
          </>
        )}

        {started && (
          <div className={`assistant ${assistOpen ? 'open' : ''}`}>
            {assistOpen && (
              <div className="assist-panel">
                <div className="log">
                  {log.length === 0 && <p className="tip">Ask for changes. With a segment selected, requests apply to it; clear the chip to edit the whole video.</p>}
                  {log.map((m, i) => (
                    <div key={i} className={`msg ${m.who}`}><small>{m.who === 'you' ? m.scope : 'AI'}</small>{m.text}</div>
                  ))}
                  {busyLabel && <div className="msg ai"><small>AI</small>{busyLabel}</div>}
                </div>
                <div className="composer">
                  <div className="scope">
                    <span className={sel !== null ? 'chip on' : 'chip'}>{scope}</span>
                    {sel !== null && <button className="x" onClick={() => setSel(null)} aria-label="Edit the whole video instead">×</button>}
                  </div>
                  <textarea value={input} onChange={(e) => setInput(e.target.value)} rows={2}
                    onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
                    placeholder={selEmpty ? 'e.g. fill this with a stat about prices' : sel !== null ? 'e.g. make this more dramatic' : 'e.g. make the whole video more cinematic'} />
                  <button onClick={send} disabled={!!busy || !input.trim()}>Send</button>
                </div>
              </div>
            )}
            <button className={`assist-fab ${busy ? 'working' : ''} ${selEmpty && !assistOpen ? 'nudge' : ''}`} onClick={() => setAssistOpen(!assistOpen)}
              aria-label={assistOpen ? 'Close assistant' : 'Open assistant'} title={busyLabel || 'Assistant'}>✦</button>
          </div>
        )}

        {toast && (
          <div className="toast" role="status">{toast.text}{toast.undo && <button className="link" onClick={undo}>Undo</button>}</div>
        )}
      </main>

      {plan && inspOpen && (
        <Inspector plan={plan} sel={sel} onClose={() => setInspOpen(false)} change={change} snapshot={snapshot} voice={voice} busy={busy}
          fixProp={(i, err) => prompt(`The 3D prop failed to build with this error: ${err}. Fix the recipe, keep the same idea.`, i)}
          findImages={findImages}
          fixLength={(i, sec) => prompt(`This segment is fixed at ${sec.toFixed(1)} seconds. Rewrite its voiceover so it takes about ${sec.toFixed(1)} seconds to say (about ${Math.max(3, Math.round(sec * 2.5))} words), keeping the meaning. Keep everything else.`, i)}
          fill={(i) => prompt('This segment is empty. Write it so it fits between the segments before and after it: title, role, narration, on-screen headline and subline, and a fitting transition and effects.', i)}
          remove={remove} />
      )}
      {plan && !inspOpen && sel !== null && (
        <button className="insp-reopen" onClick={() => setInspOpen(true)} aria-label="Open inspector" title="Open inspector">‹</button>
      )}

      {busyLabel && (
        <div className="progress" role="progressbar" aria-label={busyLabel}
          aria-valuenow={gen ? Math.round((gen.at / gen.stages.length) * 100) : undefined} aria-valuemin={0} aria-valuemax={100}>
          <div className="progress-track">
            {gen ? <i style={{ width: `${(gen.at / gen.stages.length) * 100}%` }} /> : null}
            <b className="progress-run" style={gen ? { left: `${(gen.at / gen.stages.length) * 100}%`, width: `${100 / gen.stages.length}%` } : undefined} />
          </div>
          <span>{gen ? `${gen.at + 1}/${gen.stages.length} · ` : ''}{busyLabel}</span>
        </div>
      )}
    </div>
  )
}
