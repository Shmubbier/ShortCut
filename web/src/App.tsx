import { Player, type PlayerRef } from '@remotion/player'
import { useEffect, useRef, useState } from 'react'
import { Canvas } from './Canvas'
import { Inspector } from './Inspector'
import { STYLES, type Style } from './video/theme'
import { ASPECTS, dims, EFFECTS, FPS, Main, planDuration, sceneStarts, TRANSITIONS, type Aspect, type Effect, type Plan, type SceneData, type Transition } from './video/Video'
import './App.css'

type Asset = { url: string; name: string; source?: string }
type Item = { type: 'transition'; name: Transition } | { type: 'effect'; name: Effect } | { type: 'asset'; url: string; name: string }
type Msg = { who: 'you' | 'ai'; text: string; scope: string }

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

export default function App() {
  const [plan, setPlanRaw] = useState<Plan | null>(null)
  const [history, setHistory] = useState<Plan[]>([])
  const [sel, setSel] = useState<number | null>(null)
  const [tab, setTab] = useState<'transition' | 'effect' | 'asset'>('transition')
  const [log, setLog] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState('') // '' | 'ai' | 'voice-all' | 'voice-<i>'
  const [style, setStyle] = useState<Style>('editorial')
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
  }
  const patchScene = (i: number, fn: (s: SceneData) => SceneData) =>
    plan && setPlan({ ...plan, scenes: plan.scenes.map((s, j) => (j === i ? fn(s) : s)) })

  useEffect(() => {
    if (plan && sel !== null && sel < plan.scenes.length) player.current?.seekTo(sceneStarts(plan)[sel] + 8)
  }, [sel]) // eslint-disable-line react-hooks/exhaustive-deps

  function apply(i: number, it: Item) {
    if (it.type === 'transition') patchScene(i, (s) => ({ ...s, transition: it.name }))
    if (it.type === 'effect') patchScene(i, (s) => (s.effects.includes(it.name) ? s : { ...s, effects: [...s.effects, it.name] }))
    if (it.type === 'asset') patchScene(i, (s) => ({ ...s, asset: it.url }))
    setSel(i)
  }

  function reorder(from: number, to: number) {
    if (!plan || from === to) return
    const scenes = [...plan.scenes]
    const [moved] = scenes.splice(from, 1)
    scenes.splice(to, 0, moved)
    setPlan({ ...plan, scenes })
    setSel(to)
  }

  const scope = sel !== null && plan ? `Segment ${sel + 1} · ${plan.scenes[sel].kind}` : plan ? 'Whole video' : 'New video'
  const say = (who: Msg['who'], text: string, s = scope) => setLog((l) => [...l, { who, text, scope: s }])
  const errText = (e: unknown) => `⚠ ${e instanceof Error ? e.message : e}`

  async function prompt(text: string, index = sel) {
    if (!text || busy) return
    const s = index !== null && plan ? `Segment ${index + 1} · ${plan.scenes[index].kind}` : scope
    say('you', text, s)
    try {
      if (!plan) {
        let bucket = assets
        if (autoImages) { // fill the bucket with topic images first, so the AI can place them in segments
          setBusy('find-auto')
          try {
            const found: Asset[] = await api('/api/assets/find', { query: text, limit: 6 })
            bucket = [...assets, ...found]
            setAssets(bucket)
            say('ai', `Found ${found.length} images for “${text}” (ScrapeGraphAI web search).`, s)
          } catch (e) {
            say('ai', `${errText(e)} · carrying on without new images.`, s)
          }
        }
        setBusy('ai')
        const p = await api('/api/plan', { topic: text, style, aspect, pace: 'punchy', assets: bucket })
        setPlan(p)
        say('ai', p.note ?? `Made ${p.scenes.length} segments.`, s)
      } else {
        setBusy('ai')
        const r = await api('/api/edit', { plan, index, instruction: text, assets })
        setPlan(r.plan)
        say('ai', r.note, s)
      }
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
    a.download = 'plan.json'
    a.click()
  }

  const items: Item[] = tab === 'transition'
    ? (Object.keys(TRANSITIONS) as Transition[]).map((name) => ({ type: 'transition', name }))
    : tab === 'effect' ? (Object.keys(EFFECTS) as Effect[]).map((name) => ({ type: 'effect', name })) : []

  const curAspect = plan?.aspect ?? aspect
  const curStyle = plan?.style ?? style
  const { w, h } = ASPECTS[curAspect]
  const tileProps = (it: Item) => ({
    draggable: true,
    onDragStart: (e: React.DragEvent) => e.dataTransfer.setData('text/plain', JSON.stringify(it)),
    onClick: () => sel !== null && apply(sel, it),
    title: sel !== null ? `Apply to segment ${sel + 1}` : 'Drag onto a segment',
  })

  return (
    <div className={`app ${plan ? 'has-plan' : ''}`}>
      <aside>
        <div className="brand">Blockcut</div>

        <section className="library">
          <div className="tabs">
            <button className={tab === 'transition' ? 'on' : ''} onClick={() => setTab('transition')}>Transitions</button>
            <button className={tab === 'effect' ? 'on' : ''} onClick={() => setTab('effect')}>Effects</button>
            <button className={tab === 'asset' ? 'on' : ''} onClick={() => setTab('asset')}>Assets{assets.length ? ` · ${assets.length}` : ''}</button>
          </div>

          {tab === 'asset' ? (
            <>
              <div className="asset-add">
                <form onSubmit={(e) => { e.preventDefault(); findImages(findQuery || plan?.title || '') }}>
                  <input value={findQuery} onChange={(e) => setFindQuery(e.target.value)} placeholder={plan ? `Find images: ${plan.title}` : 'Find images for a topic'} aria-label="Topic to find images for" />
                  <button type="submit" disabled={!!busy || !(findQuery || plan?.title)}>{busy === 'find' ? 'Searching…' : 'Find'}</button>
                </form>
                <label className="upload">Upload<input type="file" accept="image/png,image/jpeg,image/webp,image/gif" multiple onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} hidden /></label>
                <form onSubmit={(e) => { e.preventDefault(); scrape() }}>
                  <input value={scrapeUrl} onChange={(e) => setScrapeUrl(e.target.value)} placeholder="Paste a page URL to grab its images" aria-label="Page URL to scrape images from" />
                  <button type="submit" disabled={!scrapeUrl.trim()}>Grab</button>
                </form>
              </div>
              <div
                className="grid assets"
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => { e.preventDefault(); if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files) }}
              >
                {assets.map((a) => (
                  <div key={a.url} className="fx asset" {...tileProps({ type: 'asset', url: a.url, name: a.name })}>
                    <img src={a.url} alt={a.name} title={a.source ? `From ${a.source}` : a.name} />
                    <span>{a.name}</span>
                    <button className="x del" onClick={(e) => { e.stopPropagation(); removeAsset(a.url) }} aria-label={`Delete ${a.name}`}>×</button>
                  </div>
                ))}
                {!assets.length && <p className="tip span">Find images for a topic, drop or upload your own, or grab them from a page. The AI picks from this bucket. Found images are other people's work: check you can use them.</p>}
              </div>
              {assetMsg && <p className="tip">{assetMsg}</p>}
            </>
          ) : (
            <div className="grid">
              {items.map((it) => it.type !== 'asset' && (
                <button key={it.name} className="fx" {...tileProps(it)}>
                  <div className={`pv pv-${it.name}`}><span>Aa</span></div>
                  {it.type === 'transition' ? TRANSITIONS[it.name] : EFFECTS[it.name]}
                </button>
              ))}
            </div>
          )}
          <p className="tip">{sel !== null ? `Click to apply to segment ${sel + 1}, or drag onto any segment.` : 'Drag onto a segment.'}</p>
        </section>

        <section className="chat">
          <div className="log">
            {log.length === 0 && <p className="tip">Describe a video to start: any topic works, from food to games. Select a segment to edit just that part.</p>}
            {log.map((m, i) => (
              <div key={i} className={`msg ${m.who}`}>
                <small>{m.who === 'you' ? m.scope : 'AI'}</small>
                {m.text}
              </div>
            ))}
            {busy === 'find-auto' && <div className="msg ai"><small>AI</small>Finding images on the web…</div>}
            {busy === 'ai' && <div className="msg ai"><small>AI</small>{plan ? 'Editing…' : 'Researching + writing…'}</div>}
          </div>
          <div className="composer">
            <div className="scope">
              <span className={sel !== null ? 'chip on' : 'chip'}>{scope}</span>
              {sel !== null && <button className="x" onClick={() => setSel(null)} aria-label="Edit whole video instead">×</button>}
            </div>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
              placeholder={!plan ? 'e.g. 45s explainer on why Filipinos love ube' : sel !== null ? 'e.g. make this punchier, use the jeepney photo' : 'e.g. make the whole thing more dramatic'}
              rows={3}
            />
            {!plan && (
              <label className="check-row"><input type="checkbox" checked={autoImages} onChange={(e) => setAutoImages(e.target.checked)} /> Find topic images first</label>
            )}
            <button onClick={send} disabled={!!busy || !input.trim()}>{plan ? 'Apply' : 'Generate'}</button>
          </div>
        </section>
      </aside>

      <main>
        <header>
          <b>{plan?.title ?? 'Untitled'}</b>
          <select value={curAspect} onChange={(e) => { const v = e.target.value as Aspect; setAspect(v); if (plan) setPlan({ ...plan, aspect: v }) }} aria-label="Aspect ratio">
            {(Object.keys(ASPECTS) as Aspect[]).map((k) => <option key={k} value={k}>{ASPECTS[k].label}</option>)}
          </select>
          <select value={curStyle} onChange={(e) => { const v = e.target.value as Style; setStyle(v); if (plan) setPlan({ ...plan, style: v }) }} aria-label="Visual style">
            {(Object.keys(STYLES) as Style[]).map((k) => <option key={k} value={k}>{STYLES[k].label}</option>)}
          </select>
          <button className="ghost" onClick={undo} disabled={!history.length}>Undo</button>
          <button className="ghost" onClick={download} disabled={!plan}>Export plan</button>
        </header>

        {plan ? (
          <>
            <div className="stage" style={{ aspectRatio: `${w} / ${h}` }}>
              <Player ref={player} component={Main} inputProps={plan} durationInFrames={planDuration(plan)} fps={FPS}
                compositionWidth={dims(plan).w} compositionHeight={dims(plan).h} style={{ width: '100%', height: '100%' }} controls loop />
            </div>
            <Canvas
              plan={plan}
              sel={sel}
              onToggle={(i) => setSel((s) => (s === i ? null : i))}
              onClear={() => setSel(null)}
              onReorder={reorder}
              onDropItem={(i, json) => { try { apply(i, JSON.parse(json)) } catch { /* not one of our tiles */ } }}
              onRemoveEffect={(i, e) => patchScene(i, (s) => ({ ...s, effects: s.effects.filter((x) => x !== e) }))}
              onRemoveAsset={(i) => patchScene(i, (s) => ({ ...s, asset: '' }))}
              onImportance={(i, lv) => patchScene(i, (s) => ({ ...s, importance: lv }))}
            />
          </>
        ) : (
          <div className="empty">Pick a format and style above, fill the asset bucket if you like, then describe your video on the left.</div>
        )}
      </main>

      {plan && (
        <Inspector plan={plan} sel={sel} setSel={setSel} change={change} snapshot={snapshot} voice={voice} busy={busy}
          fixProp={(i, err) => prompt(`The 3D prop failed to build with this error: ${err}. Fix the recipe, keep the same idea.`, i)}
          findImages={findImages} />
      )}
    </div>
  )
}
