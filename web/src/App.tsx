import { Player, type PlayerRef } from '@remotion/player'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Canvas } from './Canvas'
import { Inspector } from './Inspector'
import { Flyout, ScriptPanel, SettingsPanel, StyleFromUrl, StylePanel, type Tile } from './Panels'
import { checkStatus, clearAccess, getAccess, reviewHeaders, saveAccess, unlock, untilText } from './review'
import { DEMO_COOK_MS, loadDemoIndex, loadDemoPlan, matchDemo, type DemoEntry, type DemoIndex, type Mode } from './demo'
import { STYLES, type Style } from './video/theme'
import { ASPECTS, dims, FPS, isEmpty, Main, planDuration, ROLES, sceneStarts, type Aspect, type Plan, type SceneData } from './video/Video'
import './App.css'
import './studio.css'

type Asset = { url: string; name: string; source?: string; license?: string; author?: string }
type AssetCandidate = { kind: 'image' | 'video' | 'model'; url: string; preview_url: string; title: string; source_page: string; license: string; author: string; width?: number; height?: number; duration?: number; format: string }
type Clip = { url: string; name: string; duration?: number } // uploaded video footage (spec §11)
type Passage = { start: number; end: number; text: string; words?: { text: string; start: number; end: number }[] }
type Item = Tile | { type: 'asset'; url: string; name: string } | { type: 'model'; url: string; name: string; license?: string; source?: string } | { type: 'clip'; url: string; name: string; duration?: number }
type Msg = { who: 'you' | 'ai'; text: string; scope: string }
type PanelId = 'assets' | 'script' | 'style' | 'settings'
// Real generation stages (spec §4A): the bar advances when a stage actually finishes, not on a timer.
type Gen = { stages: string[]; at: number }

// Set by App while in live mode: called when live access ends or the backend fails, so the app drops back to demo.
let onLiveLost: (() => void) | null = null

async function api(path: string, body?: unknown) {
  const headers = reviewHeaders()
  let r: Response
  try { r = await fetch(path, { method: body === undefined ? 'GET' : 'POST', body: body === undefined ? undefined : JSON.stringify(body), headers }) }
  catch (e) { onLiveLost?.(); throw e }
  const text = await r.text()
  if (r.status === 401 || r.status === 429 || r.status >= 500) onLiveLost?.()
  if (!text) throw new Error('API server not running — start it with: .venv/Scripts/python server.py')
  if (!r.ok && !text.trimStart().startsWith('{')) throw new Error(`${r.status} ${r.statusText}`) // e.g. an HTML 404 for a route that doesn't exist yet
  const j = JSON.parse(text)
  // Slow routes answer 200 with keep-alive spaces, so their errors arrive as a 200 {"error": ...} (server.py reply_slow).
  if (!r.ok || (j && typeof j === 'object' && !Array.isArray(j) && Object.keys(j).length === 1 && 'error' in j)) throw new Error(j.error)
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
// ShortCut mark: a play button with a diagonal cut through it.
export const Logo = ({ size = 34 }: { size?: number }) => (
  <svg className="logo" width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
    <rect width="40" height="40" rx="11" fill="var(--accent)" />
    <path d="M15 11.5v17l14-8.5z" fill="#fff" />
    <path d="M9 31 31 9" stroke="var(--accent)" strokeWidth="3.2" strokeLinecap="round" />
  </svg>
)

function UnlockDialog({ onClose, onDone }: { onClose: () => void; onDone: (name: string, expiresAt: string) => void }) {
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [err, setErr] = useState('')
  const [pending, setPending] = useState(false)
  async function submit(e: React.FormEvent) {
    e.preventDefault()
    const n = name.trim()
    if (n.length < 2 || n.length > 40) return setErr('Enter your name (2-40 characters)')
    if (!code.trim()) return setErr('Enter the reviewer code')
    setPending(true); setErr('')
    const r = await unlock(code.trim(), n)
    setPending(false)
    if (!r.ok) return setErr(r.error)
    saveAccess({ code: code.trim(), name: r.name })
    onDone(r.name, r.expiresAt)
  }
  return (
    <div className="unlock-back" onClick={onClose}>
      <form className="unlock" role="dialog" aria-label="Reviewer access" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h2>Reviewer access</h2>
        <label>Code<input value={code} onChange={(e) => setCode(e.target.value)} autoFocus autoComplete="off" /></label>
        <label>Your name<input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} autoComplete="off" /></label>
        {err && <p className="err">{err}</p>}
        <div className="unlock-actions"><button type="button" className="ghost" onClick={onClose}>Cancel</button><button type="submit" disabled={pending}>Unlock live generation</button></div>
      </form>
    </div>
  )
}

const greeting = () => { const h = new Date().getHours(); return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening' }

// Starter prompts on the empty start screen: each fills the composer and picks a format.
const STARTERS = [
  { label: 'Explainer', text: 'A 45-second explainer on why Filipinos love ube', content: 'explainer' },
  { label: 'Story', text: 'The story of how the jeepney was born from leftover army jeeps', content: 'story' },
  { label: 'Listicle', text: '5 Manila street foods you have to try', content: 'listicle' },
  { label: '3D showcase', text: 'How a city bus route works: the depot, the stops and the fare', content: 'showcase', style: '3d' },
]

// Theme (mockup branch): light, dark, or follow the system. Sets data-theme on <html>; remembered in this browser.
type ThemeMode = 'light' | 'dark' | 'system'
const systemDark = () => { try { return matchMedia('(prefers-color-scheme: dark)').matches } catch { return false } }
const readMode = (): ThemeMode => { try { const m = localStorage.getItem('shortcut.theme'); return m === 'light' || m === 'dark' ? m : 'system' } catch { return 'system' } }
const applyMode = (m: ThemeMode) => { document.documentElement.dataset.theme = m === 'system' ? (systemDark() ? 'dark' : 'light') : m }
applyMode(readMode())
function useThemeMode() {
  const [mode, setState] = useState<ThemeMode>(readMode)
  useEffect(() => {
    const sync = () => setState(readMode())
    const mq = matchMedia('(prefers-color-scheme: dark)')
    const onSystem = () => { if (readMode() === 'system') { applyMode('system'); sync() } } // OS switched while on "System"
    window.addEventListener('shortcut-theme', sync)
    mq.addEventListener('change', onSystem)
    return () => { window.removeEventListener('shortcut-theme', sync); mq.removeEventListener('change', onSystem) }
  }, [])
  const setMode = (m: ThemeMode) => {
    try { localStorage.setItem('shortcut.theme', m) } catch { /* private mode */ }
    applyMode(m)
    window.dispatchEvent(new Event('shortcut-theme')) // keeps the pill and the corner button in step
  }
  return [mode, setMode] as const
}
const SUN = <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
const MOON = <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></svg>
const SCREEN = <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8M12 16v4" /></svg>
// Start screen: pill selector, before anything is prompted.
function ThemePill() {
  const [mode, setMode] = useThemeMode()
  const options: [ThemeMode, string, ReactNode][] = [['light', 'Light', SUN], ['dark', 'Dark', MOON], ['system', 'System', SCREEN]]
  return (
    <div className="theme-pill" role="radiogroup" aria-label="Theme">
      {options.map(([m, label, icon]) => (
        <button key={m} role="radio" aria-checked={mode === m} className={mode === m ? 'on' : ''} onClick={() => setMode(m)}>{icon}{label}</button>
      ))}
    </div>
  )
}
// Editor: a quick light/dark flip in the corner.
function ThemeToggle() {
  const [, setMode] = useThemeMode()
  const dark = document.documentElement.dataset.theme === 'dark'
  return (
    <button className="theme-toggle" onClick={() => setMode(dark ? 'light' : 'dark')} aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'} title={dark ? 'Light mode' : 'Dark mode'}>
      {dark ? SUN : MOON}
    </button>
  )
}

const SAVE_KEY = 'blockcut.project.v1' // storage key kept from the old name so saved projects survive
const saved = (() => { try { return JSON.parse(localStorage.getItem(SAVE_KEY) ?? 'null') as { plan: Plan | null; log: Msg[]; clips?: Clip[] } | null } catch { return null } })()
// Footage endpoints are built on the server side (HANDOFF.md, Codex brief); a 404 means that part isn't installed yet.
const FOOTAGE_MISSING = 'The footage API is unavailable. Start or restart server.py, then try again.'

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
  const [newStyle, setNewStyle] = useState(false) // start screen: 'New style from a YouTube link' open
  const [assistOpen, setAssistOpen] = useState(false)
  const [log, setLog] = useState<Msg[]>(saved?.log ?? [])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState('') // '' | 'ai' | 'gen' | 'voice-all' | 'voice-<i>' | 'find' | 'find-<i>'
  const [gen, setGen] = useState<Gen | null>(null)
  const [leaving, setLeaving] = useState(false) // hero prompt shrinking into the assistant icon
  const [cookStart, setCookStart] = useState(0)
  const [now, setNow] = useState(Date.now())
  const [heroError, setHeroError] = useState('')
  const [reveal, setReveal] = useState(Infinity) // cards shown so far during the reveal
  const [previewIn, setPreviewIn] = useState(!!saved?.plan)
  const [mode, setMode] = useState<Mode>('demo') // 'demo': ready videos, no backend; 'live': unlocked with a reviewer code
  const [unlockOpen, setUnlockOpen] = useState(false)
  const [expiresAt, setExpiresAt] = useState('')
  const [who, setWho] = useState('')
  const [demoMiss, setDemoMiss] = useState<DemoIndex | null>(null) // topic matched no demo video: offer the ones we have
  const [toast, setToast] = useState<{ text: string; undo: boolean; code?: boolean } | null>(null)
  const [style, setStyle] = useState<Style | 'auto'>('auto')
  const [content, setContent] = useState('auto') // content style id (explainer, story, listicle, …, or a custom one)
  const [contentStyles, setContentStyles] = useState<{ id: string; label: string; description: string; custom?: boolean }[]>([])
  const [aspect, setAspect] = useState<Aspect>('9:16')
  const [assets, setAssets] = useState<Asset[]>([])
  const [scrapeUrl, setScrapeUrl] = useState('')
  const [findQuery, setFindQuery] = useState('')
  const [searchKinds, setSearchKinds] = useState<Array<'image'|'video'|'model'>>(['image','video','model'])
  const [searchResults, setSearchResults] = useState<AssetCandidate[]>([])
  const [models, setModels] = useState<Array<{url:string;name:string;source?:string;license?:string;thumbnail?:string|null}>>([])
  const [autoImages, setAutoImages] = useState(true)
  const [assetMsg, setAssetMsg] = useState('')
  const [clips, setClips] = useState<Clip[]>(saved?.clips ?? [])
  const [footage, setFootage] = useState<{ clip: Clip; passages: Passage[] } | null>(null) // transcript awaiting review
  const [renderUrl, setRenderUrl] = useState('')
  const player = useRef<PlayerRef>(null)
  const planRef = useRef(plan)
  planRef.current = plan

  // Live mode: a failure or ended access drops back to demo and keeps the open plan on screen.
  useEffect(() => {
    if (mode !== 'live') { onLiveLost = null; return }
    onLiveLost = () => {
      onLiveLost = null
      setMode('demo')
      setToast({ text: "Live access ended or is unavailable. You're back in demo mode; your video is kept.", undo: false })
    }
    return () => { onLiveLost = null }
  }, [mode])
  // On load: if the site is open and this browser remembers a code, quietly switch to live.
  useEffect(() => {
    const a = getAccess()
    if (!a) return
    checkStatus().then(async (st) => {
      if (!st.open) return
      const u = await unlock(a.code, a.name)
      if (u.ok) { setWho(u.name); setExpiresAt(u.expiresAt); setMode('live') } else clearAccess()
    })
  }, [])
  useEffect(() => { api('/api/assets').then(setAssets).catch(() => {}); api('/api/models3d').then(setModels).catch(() => {}) }, [mode])
  useEffect(() => { if (panel === 'assets') api('/api/models3d').then(setModels).catch(() => {}) }, [panel, plan?.scenes.length]) // generation adds Polyfork models
  useEffect(() => {
    const refresh = () => {
      api('/api/styles').then(setContentStyles).catch(() => fetch('/demo/styles.json').then((r) => r.json()).then(setContentStyles).catch(() => {})) // no backend: the bundled list
    }
    refresh()
    window.addEventListener('blockcut-styles-updated', refresh)
    return () => window.removeEventListener('blockcut-styles-updated', refresh)
  }, [])
  useEffect(() => { if (!gen) return; const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t) }, [gen])
  useEffect(() => { // autosave (skipped mid-reveal so a refresh can't save a half-shown storyboard)
    if (gen) return
    try { localStorage.setItem(SAVE_KEY, JSON.stringify({ plan, log: log.slice(-60), clips })) } catch { /* storage full or blocked */ }
  }, [plan, log, gen, clips])

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
    if (it.type === 'model') patchScene(i, (s) => ({ ...s, model: { url: it.url, title: it.name, license: it.license, source: it.source }, prop: null }))
    if (it.type === 'clip') patchScene(i, (s) => assignClip(s, it))
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

  // A clip on a segment: the segment becomes footage, trimmed to its current length (or the whole clip if shorter).
  const assignClip = (s: SceneData, c: Clip): SceneData => {
    const len = s.length ?? 5
    const end = Math.round((c.duration ? Math.min(c.duration, len) : len) * 10) / 10
    return { ...s, role: 'footage', media: { type: 'video', url: c.url, name: c.name, duration: c.duration, trimStart: 0, trimEnd: end }, length: Math.max(1, end) }
  }
  const footageError = (e: unknown) => setAssetMsg(/404|Not Found/i.test(String(e)) ? FOOTAGE_MISSING : errText(e))

  // Footage workflow (spec §3B): upload -> transcript (editable) -> storyboard. Endpoints per HANDOFF.md.
  async function uploadClip(f: File, transcribe = false) {
    if (mode === 'demo') return needsCode('Footage upload')
    setBusy('upload')
    setAssetMsg(`Uploading ${f.name}…`)
    try {
      const c: Clip = await api('/api/footage/upload', { name: f.name, data: await readDataUrl(f) })
      setClips((cs) => [...cs, c])
      setAssetMsg(`Added ${c.name}`)
      setBusy('')
      if (transcribe) await transcribeClip(c)
    } catch (e) {
      footageError(e)
      setBusy('')
    }
  }
  async function transcribeClip(c: Clip) {
    setBusy('transcribe')
    setPanel('assets')
    try {
      const r: { segments: Passage[] } = await api('/api/footage/transcribe', { url: c.url })
      setFootage({ clip: c, passages: r.segments.map((x) => ({ start: x.start, end: x.end, text: x.text.trim(), words: x.words })) })
    } catch (e) {
      footageError(e)
    } finally {
      setBusy('')
    }
  }
  async function storyboardFromFootage() {
    if (!footage) return
    if (plan && !confirm('Build a new storyboard from this footage? It replaces the current video (Undo can bring it back).')) return
    const stages = ['Grouping the transcript into scenes', 'Building the storyboard', 'Preparing the preview']
    setBusy('gen'); setGen({ stages, at: 0 })
    try {
      const p: Plan & { note?: string } = await api('/api/footage/storyboard', { url: footage.clip.url, transcript: footage.passages, style, aspect })
      setGen({ stages, at: 1 })
      setReveal(0); setPreviewIn(false)
      setPlan(p)
      for (let k = 1; k <= p.scenes.length; k++) { await wait(260); setReveal(k) }
      setGen({ stages, at: 2 })
      await wait(150); setPreviewIn(true); await wait(400)
      say('ai', p.note ?? `Built ${p.scenes.length} segments from ${footage.clip.name}.`, 'Footage')
      setFootage(null)
    } catch (e) {
      footageError(e)
    } finally {
      setReveal(Infinity); setGen(null); setBusy('')
    }
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

  // First prompt: image search runs alongside writing so discovery doesn't hold up the storyboard.
  // The hero card stays on screen and "cooks" (real stages + elapsed time) until the whole plan is ready.
  // Only then does it shrink into the assistant and the workspace animate in: the card-by-card population
  // is a presentation of finished data, so nobody stares at a half-empty workspace.
  async function generate(text: string, demo?: DemoEntry) {
    const live = mode === 'live'
    const stages = [...(autoImages && live ? ['Finding images'] : []), 'Researching & writing the script']
    setHeroError(''); setDemoMiss(null)
    setBusy('gen')
    setGen({ stages, at: 0 })
    setCookStart(Date.now())
    say('you', text, 'New video')
    let completed = 0
    const stageDone = () => setGen({ stages, at: ++completed })
    try {
      const imageTask: Promise<Asset[]> = autoImages && live ? api('/api/assets/find', { query: text, limit: 6 }).then((found: Asset[]) => {
        setAssets((current) => [...current, ...found])
        say('ai', `Found ${found.length} images for “${text}” (ScrapeGraphAI web search).`, 'New video')
        stageDone()
        return found
      }).catch((e) => {
        say('ai', `${errText(e)} · carrying on without new images.`, 'New video')
        stageDone()
        return []
      }) : Promise.resolve([])
      const demoPlan = async (): Promise<Plan & { note?: string }> => {
        const idx = await loadDemoIndex()
        const entry = demo ?? matchDemo(text, idx)
        if (!entry) { setDemoMiss(idx); throw new Error('no demo') }
        await wait(DEMO_COOK_MS)
        return loadDemoPlan(entry)
      }
      const planTask: Promise<Plan & { note?: string }> = (live ? api('/api/plan', { topic: text, style, content, aspect, pace: 'punchy', assets }) : demoPlan())
        .then((result: Plan & { note?: string }) => { stageDone(); return result })
      const [p, found] = await Promise.all([planTask, imageTask])
      if (found.length) {
        let visual = 0
        p.scenes = p.scenes.map((s) => {
          if (s.asset || !['image', 'broll'].includes(s.role ?? '') && !['fact', 'stat'].includes(s.kind)) return s
          const asset = found[visual++]
          return asset ? { ...s, asset: asset.url } : s
        })
      }
      await wait(500)
      setLeaving(true) // hero eases into the assistant corner…
      await wait(450)
      setReveal(0)
      setPreviewIn(false)
      setHistory([])
      setPlanRaw(p) // …then the workspace appears and populates
      setLeaving(false)
      await wait(300)
      for (let k = 1; k <= p.scenes.length; k++) { await wait(220); setReveal(k) }
      await wait(150)
      setPreviewIn(true)
      await wait(500)
      say('ai', p.note ?? `Made ${p.scenes.length} segments.`, 'New video')
    } catch (e) {
      if (!live && e instanceof Error && e.message === 'no demo') setHeroError('Live generation is for reviewers. Try one of the demo videos:')
      else { say('ai', errText(e), 'New video'); setHeroError(errText(e)) }
    } finally {
      setReveal(Infinity)
      setGen(null)
      setBusy('')
    }
  }

  const signOut = () => { clearAccess(); setMode('demo') }
  const liveChip = mode === 'live' && (
    <span className="live-chip">Live · {who}{expiresAt && ` · until ${untilText(expiresAt)}`} <button className="link" onClick={signOut}>Sign out</button></span>
  )

  // Demo mode: anything that needs the backend shows this notice instead.
  function needsCode(action: string) {
    setAssetMsg(`${action} needs a reviewer code.`)
    setToast({ text: 'Needs a reviewer code', undo: false, code: true })
  }

  async function prompt(text: string, index = sel, extra: Record<string, unknown> = {}) {
    if (!text || busy) return
    if (!plan) return generate(text)
    if (mode === 'demo') return needsCode('AI edits')
    const s = scopeOf(index)
    setBusy('ai')
    say('you', text, s)
    try {
      const r = await api('/api/edit', { plan, index, instruction: text, assets, ...extra })
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
    if (mode === 'demo') return needsCode('Voiceover')
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

  async function renderVideo() {
    if (!plan || busy) return
    if (mode === 'demo') return needsCode('Rendering')
    setBusy('render')
    setRenderUrl('')
    setAssetMsg('Starting MP4 render…')
    try {
      const job: { id: string; status: string } = await api('/api/render', { plan })
      for (let attempt = 0; attempt < 600; attempt++) {
        await wait(2000)
        const status = await api(`/api/render/${job.id}`) as { status: string; progress?: number; url?: string; error?: string }
        if (status.status === 'done' && status.url) {
          setRenderUrl(status.url)
          setAssetMsg('MP4 render complete')
          return
        }
        if (status.status === 'error') throw new Error(status.error || 'MP4 render failed')
      }
      throw new Error('MP4 render is taking longer than expected; check the API server log')
    } catch (e) {
      setAssetMsg(errText(e))
    } finally {
      setBusy('')
    }
  }

  async function addFiles(files: FileList | null) {
    if (!files?.length) return
    if (mode === 'demo') return needsCode('Uploading images')
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
    if (mode === 'demo') return needsCode('Grabbing images from a page')
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
    if (mode === 'demo') return needsCode('Image search')
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

  async function searchMedia(query: string) {
    if (!query.trim() || busy || !searchKinds.length) return
    if (mode === 'demo') return needsCode('Media search')
    setBusy('find'); setAssetMsg('Searching Commons, Openverse, NASA and image search…')
    try {
      const r = await api('/api/assets/search', { query, kinds: searchKinds, limit: 8 })
      setSearchResults(r.candidates ?? [])
      setAssetMsg(`Found ${r.candidates?.length ?? 0} candidates. Import a result to add it to the library.`)
    } catch (e) { setAssetMsg(errText(e)) } finally { setBusy('') }
  }

  async function importMedia(candidate: AssetCandidate) {
    if (mode === 'demo') return needsCode('Importing media')
    setAssetMsg(`Importing ${candidate.title}…`)
    try {
      const item = await api('/api/assets/import', { candidate })
      if (item.kind === 'image') setAssets((a) => [...a, item])
      else if (item.kind === 'video') setClips((a) => [...a, item])
      else setModels((a) => [...a, item])
      setAssetMsg(item.kind === 'video' && item.duration > 60
        ? `Imported ${item.name} (${item.duration.toFixed(1)}s). Drag it to a segment to use a short slice.`
        : `Imported ${item.name} · ${item.license || 'licence unknown'}`)
    } catch (e) { setAssetMsg(`Could not import: ${errText(e)}`) }
  }

  async function removeAsset(url: string) {
    await api('/api/assets/delete', { url }).catch(() => {})
    setAssets((a) => a.filter((x) => x.url !== url))
  }

  function download() {
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([JSON.stringify(plan, null, 2)], { type: 'application/json' }))
    a.download = 'shortcut-project.json'
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

  const started = !!plan || !!footage || busy === 'upload' || busy === 'transcribe'
  const cooking = !!gen && !plan
  const selEmpty = plan && sel !== null && plan.scenes[sel] ? isEmpty(plan.scenes[sel]) : false
  const busyLabel = gen ? '' // generation shows its progress on the hero card, not the bottom bar
    : busy === 'ai' ? 'Applying your edit…' : busy === 'voice-all' ? 'Voicing all segments…' : busy.startsWith('voice-') ? 'Voicing the segment…'
      : busy.startsWith('find') ? 'Searching the web for images…' : busy === 'upload' ? 'Uploading footage…' : busy === 'transcribe' ? 'Transcribing the footage (Whisper)…' : busy === 'render' ? 'Rendering the MP4…' : ''
  const curAspect = plan?.aspect ?? aspect
  const { w, h } = ASPECTS[curAspect]

  const assetsPanel = (
    <>
      <div className="asset-add">
        <form onSubmit={(e) => { e.preventDefault(); searchMedia(findQuery || plan?.title || '') }}>
          <input value={findQuery} onChange={(e) => setFindQuery(e.target.value)} placeholder={plan ? `Search assets: ${plan.title}` : 'Search images, video or 3D'} aria-label="Topic to search for assets" />
          <button type="submit" disabled={!!busy || !(findQuery || plan?.title)}>{busy === 'find' ? 'Searching…' : 'Search'}</button>
        </form>
        <div className="kind-chips" role="group" aria-label="Search for">{(['image','video','model'] as const).map((kind) => <button key={kind} type="button" aria-pressed={searchKinds.includes(kind)} className={searchKinds.includes(kind) ? 'on' : ''} onClick={() => setSearchKinds((k) => k.includes(kind) ? k.filter((x) => x !== kind) : [...k, kind])}>{kind === 'model' ? '3D' : kind === 'image' ? 'Images' : 'Video'}</button>)}</div>
        <label className="upload">Upload images<input type="file" accept="image/png,image/jpeg,image/webp,image/gif" multiple onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} hidden /></label>
        <form onSubmit={(e) => { e.preventDefault(); scrape() }}>
          <input value={scrapeUrl} onChange={(e) => setScrapeUrl(e.target.value)} placeholder="Paste a page URL to grab its images" aria-label="Page URL to scrape images from" />
          <button type="submit" disabled={!scrapeUrl.trim()}>Grab</button>
        </form>
      </div>
      {!!searchResults.length && <div className="grid assets search-results">{searchResults.map((c) => <article key={`${c.kind}:${c.url}`} className="fx asset result" title={`${c.title} · ${c.license}`}>
        {c.kind === 'image' ? <img src={c.preview_url} alt="" loading="lazy" /> : c.kind === 'video' ? <video src={c.url} poster={c.preview_url} muted preload="metadata" /> : c.preview_url && c.preview_url !== c.url ? <img src={c.preview_url} alt="" loading="lazy" className="model-thumb" /> : <div className="model-preview"><svg className="model-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2 3 7v10l9 5 9-5V7z M3 7l9 5 9-5 M12 12v10" /></svg></div>}
        <button className="import-icon" onClick={() => importMedia(c)} aria-label={`Import ${c.title}`}>+</button>
      </article>)}</div>}
      <div className="grid assets" onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files) }}>
        {assets.map((a) => (
          <div key={a.url} className="fx asset" {...tileProps({ type: 'asset', url: a.url, name: a.name })}>
            <img src={a.url} alt={a.name} title={[a.name, a.license, a.source && `From ${a.source}`].filter(Boolean).join(' · ')} />
            <button className="x del" onClick={(e) => { e.stopPropagation(); removeAsset(a.url) }} aria-label={`Delete ${a.name}`}>×</button>
          </div>
        ))}
        {!assets.length && <p className="tip span">Find images for a topic, drop or upload your own, or grab them from a page. Found images are other people's work: check you can use them.</p>}
      </div>
      {assetMsg && <p className="tip">{assetMsg}</p>}

      <h3>Video footage</h3>
      <label className="upload">{busy === 'upload' ? 'Uploading…' : 'Upload a video clip'}
        <input type="file" accept="video/mp4,video/webm,video/quicktime" onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadClip(f); e.target.value = '' }} hidden disabled={!!busy} /></label>
      {footage && (
        <div className="footage-review">
          <b>Transcript of {footage.clip.name}</b>
          <small className="tip">Fix any misheard words, then build the storyboard. Each passage keeps its timestamps.</small>
          {footage.passages.map((p, k) => (
            <label key={k}>{p.start.toFixed(1)}s–{p.end.toFixed(1)}s
              <textarea rows={2} value={p.text} onChange={(e) => setFootage({ ...footage, passages: footage.passages.map((x, j) => (j === k ? { ...x, text: e.target.value } : x)) })} />
            </label>
          ))}
          <div className="row">
            <button onClick={storyboardFromFootage} disabled={!!busy}>Build storyboard from footage</button>
            <button className="link" onClick={() => setFootage(null)}>Cancel</button>
          </div>
        </div>
      )}
      <div className="clips">
        {clips.map((c) => (
          <div key={c.url} className="clip" {...tileProps({ type: 'clip', url: c.url, name: c.name, duration: c.duration })}>
            <video src={c.url} muted preload="metadata" />
            <span>{c.name}{c.duration ? ` · ${c.duration.toFixed(1)}s` : ''}</span>
            <button className="link" onClick={(e) => { e.stopPropagation(); transcribeClip(c) }} disabled={!!busy}>Transcribe → storyboard</button>
          </div>
        ))}
      </div>
      {!!models.length && <><h3>3D models</h3><div className="clips">{models.map((m) => <div key={m.url} className="clip model-tile" {...tileProps({ type: 'model', url: m.url, name: m.name, license: m.license, source: m.source })}>{m.thumbnail ? <img src={m.thumbnail} alt={m.name} loading="lazy" /> : <div className="model-preview"><svg className="model-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2 3 7v10l9 5 9-5V7z M3 7l9 5 9-5 M12 12v10" /></svg></div>}</div>)}</div></>}
      <p className="tip">Drag an image or clip onto a storyboard card or the inspector's Media box. The same asset can go on several segments.</p>
    </>
  )

  return (
    <div className={`studio ${started ? 'started' : ''}`}>
      {started ? <ThemeToggle /> : <ThemePill />}
      {started && (
        <nav className="rail" aria-label="Panels">
          <div className="rail-brand" title="ShortCut"><Logo size={34} /></div>
          {(Object.keys(ICONS) as PanelId[]).map((id, k) => (
            <button key={id} className={`rail-btn ${panel === id ? 'on' : ''}`} style={{ animationDelay: `${k * 70}ms` }}
              data-label={ICONS[id].label} aria-label={ICONS[id].label} onClick={() => setPanel(panel === id ? null : id)}>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS[id].path} /></svg>
            </button>
          ))}
        </nav>
      )}

      {started && panel && (
        <Flyout title={ICONS[panel].label} onClose={() => setPanel(null)} wide={panel === 'assets'}>
          {panel === 'assets' && assetsPanel}
          {panel === 'script' && plan && <ScriptPanel plan={plan} change={change} snapshot={snapshot} sel={sel} onSelect={select} />}
          {panel === 'style' && plan && <StylePanel plan={plan} change={change} snapshot={snapshot} tileProps={tileProps} busy={!!busy} locked={mode === 'demo' ? () => needsCode('Learning a style from YouTube') : undefined}
            onRestyle={(st) => { snapshot(); prompt(`Restyle this video as “${st.label}”`, null, { content: st.id }) }} />}
          {panel === 'settings' && plan && <SettingsPanel plan={plan} change={(p) => {
            if (p.voiceRate !== plan.voiceRate) p = { ...p, scenes: p.scenes.map((s) => ({ ...s, audio: null, words: s.media?.type === 'video' && !s.audio ? s.words : [] })) }
            change(p)
          }} snapshot={snapshot} voice={voice} busy={busy} onExport={download} onRender={renderVideo} renderUrl={mode === 'demo' ? plan.exportUrl ?? '' : renderUrl} />}
          {!plan && panel !== 'assets' && <p className="tip">Available once the storyboard is ready.</p>}
        </Flyout>
      )}

      <main className={assistOpen && started ? 'assist-open' : ''}>
        {started && (
          <header>
            <b>{plan?.title ?? 'Generating…'}</b>
            {plan?.contentStyle && <span className="chip" title="Content style: ask the assistant to change it, e.g. 'make it a story'">{contentStyles.find((c) => c.id === plan.contentStyle)?.label ?? plan.contentStyle}</span>}
            {liveChip}
            <button className="ghost" onClick={undo} disabled={!history.length}>Undo</button>
            <button className="ghost" onClick={newProject} disabled={!!gen}>New video</button>
          </header>
        )}

        {(!started || leaving) && (
          <div className={`hero ${leaving ? 'leaving' : ''} ${cooking ? 'cooking' : 'empty'}`}>
            {cooking || leaving ? (
              <div className="cook" role="status" aria-live="polite">
                <svg className="pot" viewBox="0 0 120 100" aria-hidden="true">
                  <path className="steam s1" d="M42 38c-6-8 6-12 0-20" /><path className="steam s2" d="M60 34c-6-8 6-12 0-20" /><path className="steam s3" d="M78 38c-6-8 6-12 0-20" />
                  <path className="pot-body" d="M22 48h76v8c0 18-14 30-38 30S22 74 22 56z" /><path className="pot-lid" d="M18 46h84" /><path className="pot-handle" d="M10 52h12M98 52h12" />
                </svg>
                <h1>Cooking up your video…</h1>
                <p className="cook-prompt">“{log.filter((m) => m.who === 'you').at(-1)?.text}”</p>
                <ol className="cook-steps">
                  {gen?.stages.map((st, k) => (
                    <li key={st} className={k < gen.at ? 'done' : k === gen.at ? 'now' : ''}>
                      <span className="mark">{k < gen.at ? '✓' : ''}</span>{st}{k === gen.at ? <em> · {Math.max(0, Math.round((now - cookStart) / 1000))}s</em> : null}
                    </li>
                  ))}
                  <li className={gen && gen.at >= gen.stages.length ? 'now' : ''}><span className="mark" />Setting up your workspace</li>
                </ol>
                <small className="tip">Researching the web and writing usually takes 40-60 s (3D: about 2 min).</small>
              </div>
            ) : (
            <>
            <div className="brand-row"><Logo size={44} /><span className="wordmark">Short<b>Cut</b></span></div>
            <div className="welcome">
              <h1>{greeting()}</h1>
            </div>
            <p className="welcome-sub">What video should we make today? ShortCut researches it, writes the script, builds the storyboard and voices it.</p>
            <div className="composer">
            <textarea value={input} onChange={(e) => setInput(e.target.value)} rows={3} autoFocus
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
              placeholder="Describe your video…" aria-label="Describe your video" />
            <div className="hero-opts">
              <select value={content} onChange={(e) => { if (e.target.value === '__new') setNewStyle(true); else setContent(e.target.value) }} aria-label="Content style"
                title={contentStyles.find((c) => c.id === content)?.description ?? 'The AI picks the format that fits your prompt'}>
                <option value="auto">Auto format (AI picks)</option>
                {contentStyles.filter((c) => !c.custom).map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
                {contentStyles.some((c) => c.custom) && <optgroup label="Your styles">
                  {contentStyles.filter((c) => c.custom).map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
                </optgroup>}
                <option value="__new">＋ New style from a YouTube link…</option>
              </select>
              <select value={style} onChange={(e) => setStyle(e.target.value as Style | 'auto')} aria-label="Visual style">
                <option value="auto">Auto style (AI picks)</option>
                {(Object.keys(STYLES) as Style[]).map((k) => <option key={k} value={k}>{STYLES[k].label}</option>)}
              </select>
              <select value={aspect} onChange={(e) => setAspect(e.target.value as Aspect)} aria-label="Format">
                {(Object.keys(ASPECTS) as Aspect[]).map((k) => <option key={k} value={k}>{ASPECTS[k].label}</option>)}
              </select>
              <label className="check-row" title="Search the web for photos of the topic"><input type="checkbox" checked={autoImages} onChange={(e) => setAutoImages(e.target.checked)} /> Images</label>
              <button className="send" onClick={send} disabled={!!busy || !input.trim()} aria-label="Generate video" title="Generate (Enter)">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
              </button>
            </div>
            </div>
            <div className="starters">
              {STARTERS.map((st) => (
                <button key={st.label} onClick={() => { setInput(st.text); setContent(st.content); if (st.style) setStyle(st.style as Style) }}>
                  <b>{st.label}</b> {st.text}
                </button>
              ))}
            </div>
            {newStyle && <div className="hero-style">
              <small className="tip">Paste a YouTube video and ShortCut learns its format, writing and cut rhythm (not its words or footage).</small>
              <StyleFromUrl onDone={(st) => { setContent(st.id); setNewStyle(false) }} locked={mode === 'demo' ? () => needsCode('Learning a style from YouTube') : undefined} />
            </div>}
            <label className="hero-footage">or start from your own video clip
              <input type="file" accept="video/mp4,video/webm,video/quicktime" onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadClip(f, true); e.target.value = '' }} hidden /></label>
            {assetMsg && <p className="tip">{assetMsg}</p>}
            {liveChip || <button className="link reviewer-link" onClick={() => setUnlockOpen(true)}>Reviewer access</button>}
            {heroError && <p className="err">{heroError}</p>}
            {demoMiss && <div className="starters">{demoMiss.plans.map((d) => <button key={d.file} onClick={() => { setDemoMiss(null); generate(d.title, d) }}><b>{d.title}</b></button>)}</div>}
            </>
            )}
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

        {unlockOpen && <UnlockDialog onClose={() => setUnlockOpen(false)} onDone={(n, e) => { setWho(n); setExpiresAt(e); setMode('live'); setUnlockOpen(false); setToast(null); setAssetMsg('') }} />}
        {toast && (
          <div className="toast" role="status">{toast.text}{toast.undo && <button className="link" onClick={undo}>Undo</button>}{toast.code && <button className="link" onClick={() => { setToast(null); setUnlockOpen(true) }}>Enter code</button>}</div>
        )}
      </main>

      {plan && inspOpen && (
        <Inspector plan={plan} sel={sel} onClose={() => setInspOpen(false)} change={change} snapshot={snapshot} voice={voice} busy={busy}
          fixProp={(i, err) => prompt(`The 3D prop failed to build with this error: ${err}. Fix the recipe, keep the same idea.`, i)}
          findImages={findImages}
          fixLength={(i, sec) => prompt(`This segment is fixed at ${sec.toFixed(1)} seconds. Rewrite its voiceover so it takes about ${sec.toFixed(1)} seconds to say (about ${Math.max(3, Math.round(sec * 2.5))} words), keeping the meaning. Keep everything else.`, i)}
          fill={(i) => prompt('This segment is empty. Write it so it fits between the segments before and after it: title, role, narration, on-screen headline and subline, and a fitting transition and effects.', i)}
          remove={remove}
          clipFor={(i, c) => patchScene(i, (s) => assignClip(s, c))} />
      )}
      {plan && !inspOpen && sel !== null && (
        <button className="insp-reopen" onClick={() => setInspOpen(true)} aria-label="Open inspector" title="Open inspector">‹</button>
      )}

      {busyLabel && (
        <div className="progress" role="progressbar" aria-label={busyLabel}
          aria-valuenow={gen ? Math.round((gen.at / gen.stages.length) * 100) : undefined} aria-valuemin={0} aria-valuemax={100}>
          <div className="progress-track">
            {gen ? <i style={{ width: `${Math.min(100, (gen.at / gen.stages.length) * 100)}%` }} /> : null}
            <b className="progress-run" style={gen ? { left: `${Math.min(100 - 100 / gen.stages.length, (gen.at / gen.stages.length) * 100)}%`, width: `${100 / gen.stages.length}%` } : undefined} />
          </div>
          <span>{gen ? `${Math.min(gen.at + 1, gen.stages.length)}/${gen.stages.length} · ` : ''}{busyLabel}</span>
        </div>
      )}
    </div>
  )
}
