import { AbsoluteFill, Audio, Easing, Img, interpolate, random, Sequence, spring, useCurrentFrame, useVideoConfig } from 'remotion'
import type { Recipe } from './bench3d/recipe'
import { Stage3D } from './Stage3D'
import { fontCss, resolveTheme, stack, type Style, type Theme, type ThemeChoice } from './theme'

export type Kind = 'title' | 'fact' | 'stat' | 'quote' | 'outro'
export type Transition = 'cut' | 'whip' | 'zoom' | 'slide' | 'flash'
export type Effect = 'shake' | 'punch' | 'invert' | 'typewriter' | 'highlight' | 'vignette'
export type Aspect = '16:9' | '9:16' | '1:1' | '4:5'
export type Word = { text: string; start: number; end: number } // seconds from the segment's audio start
export type SceneData = {
  id: string; kind: Kind; headline: string; sub: string; value: string; transition: Transition; effects: Effect[]
  asset?: string; prop?: Recipe | null
  purpose?: string; voiceover?: string; importance?: Importance; audio?: { url: string; duration: number } | null; words?: Word[]; captionSource?: 'whisper' | 'tts'
}
export type Plan = {
  title: string; style: Style; pace: 'punchy' | 'documentary'; aspect?: Aspect; theme?: ThemeChoice; captions?: boolean; voice?: string
  scenes: SceneData[]
}

// The library panel reads these; the server's EDITING_GUIDE describes the same names to Claude.
export const TRANSITIONS: Record<Transition, string> = {
  cut: 'Hard cut', whip: 'Whip pan', zoom: 'Zoom punch', slide: 'Slide up', flash: 'White flash',
}
export const EFFECTS: Record<Effect, string> = {
  shake: 'Camera shake', punch: 'Slow push-in', invert: 'Invert colors', typewriter: 'Typewriter text', highlight: 'Marker highlight', vignette: 'Vignette',
}
export const ASPECTS: Record<Aspect, { w: number; h: number; label: string }> = {
  '16:9': { w: 1920, h: 1080, label: '16:9 · YouTube' },
  '9:16': { w: 1080, h: 1920, label: '9:16 · Reels / TikTok / Shorts' },
  '1:1': { w: 1080, h: 1080, label: '1:1 · Feed square' },
  '4:5': { w: 1080, h: 1350, label: '4:5 · Feed portrait' },
}
export const dims = (p: Plan) => ASPECTS[p.aspect ?? '16:9']

export const FPS = 30
const OVERLAP = 6 // frames scenes overlap so transitions have something to cover

// Editing presets: a human editor varies hold length with how much there is to read and how much the line matters.
// Length comes from the script (or the voiceover, once generated); importance stretches or tightens it:
// a key beat lingers after the line lands, a quick connective beat cuts away almost at once.
const PACE = { punchy: { base: 40, perWord: 5 }, documentary: { base: 75, perWord: 9 } }
export type Importance = 1 | 2 | 3
export const IMPORTANCE: Record<Importance, { label: string; scale: number; hold: number }> = {
  1: { label: 'Quick', scale: 0.8, hold: 4 }, // hold = frames after the voiceover ends
  2: { label: 'Normal', scale: 1, hold: 12 },
  3: { label: 'Key', scale: 1.3, hold: 30 },
}
export const timing = (s: SceneData, pace: Plan['pace']) => {
  const imp = IMPORTANCE[s.importance ?? 2] ?? IMPORTANCE[2]
  if (s.audio?.duration) {
    const voice = Math.ceil(s.audio.duration * FPS)
    return { frames: Math.max(45, voice + OVERLAP + imp.hold), source: 'voice' as const, voice, hold: imp.hold }
  }
  const words = `${s.headline} ${s.sub}`.split(/\s+/).length
  const base = PACE[pace].base + words * PACE[pace].perWord + (s.kind === 'stat' ? 20 : 0) + (s.effects?.includes('typewriter') ? 15 : 0) + (s.prop ? 30 : 0)
  return { frames: Math.round(base * imp.scale), source: 'script' as const, words, voice: 0, hold: 0 }
}
export const sceneLen = (s: SceneData, pace: Plan['pace']) => timing(s, pace).frames
export const sceneStarts = (p: Plan) => {
  let at = 0
  return p.scenes.map((s) => { const from = at; at += sceneLen(s, p.pace) - OVERLAP; return from })
}
export const planDuration = (p: Plan) =>
  p.scenes.reduce((t, s) => t + sceneLen(s, p.pace) - OVERLAP, OVERLAP) || FPS

// Stepped frame for pixel style; real frame otherwise.
const useF = (t: Theme) => {
  const f = useCurrentFrame()
  return f - (f % t.step)
}

const Words = ({ text, t, size, color, fx, delay = 0, mark = false }: { text: string; t: Theme; size: number; color: string; fx: Effect[]; delay?: number; mark?: boolean }) => {
  const f = useF(t)
  const { fps } = useVideoConfig()
  const style = { fontFamily: stack(t.display), fontWeight: 800, fontSize: size, lineHeight: 1.05, color, textTransform: 'uppercase' as const }
  const bouncy = t.style === '2d'
  const swipe = interpolate(f, [delay + 14, delay + 28], [0, 100], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.quad) })
  const words = fx.includes('typewriter') ? (
    <div style={style}>
      {text.slice(0, Math.max(0, Math.floor((f - delay) * 0.9)))}
      <span style={{ opacity: f % 16 < 8 ? 1 : 0, color: t.accent }}>▌</span>
    </div>
  ) : (
    <div style={{ ...style, display: 'flex', flexWrap: 'wrap', gap: '0 0.28em' }}>
      {text.split(' ').map((w, i) => {
        const s = spring({ frame: f - delay - i * 3, fps, config: bouncy ? { damping: 7, mass: 0.7 } : { damping: 11, mass: 0.6 } }) // overshoot + settle
        const squash = bouncy ? `scale(${1 + (1 - s) * 0.3}, ${1 - (1 - s) * 0.3})` : ''
        return (
          <span key={i} style={{ display: 'inline-block', opacity: s > 0.01 ? 1 : 0, transform: `translateY(${(1 - s) * 60}px) rotate(${(1 - s) * (i % 2 ? 4 : -4)}deg) ${squash}` }}>
            {w}
          </span>
        )
      })}
    </div>
  )
  if (!mark && !fx.includes('highlight')) return words
  return (
    <div style={{ position: 'relative', width: 'fit-content' }}>
      <div style={{ position: 'absolute', left: -10, bottom: 4, height: '38%', width: `${swipe}%`, background: t.accent, opacity: 0.35 }} />
      {words}
    </div>
  )
}

const Sub = ({ text, t, color, delay }: { text: string; t: Theme; color: string; delay: number }) => {
  const f = useF(t)
  const o = interpolate(f, [delay, delay + 10], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
  return text ? <div style={{ fontFamily: stack(t.body), fontSize: t.step > 1 ? 22 : 38, color, opacity: o, marginTop: 36, maxWidth: 1300, lineHeight: 1.5 }}>{text}</div> : null
}

// Asset as a cutout: taped paper (editorial/3D), thick outlined sticker (2D), hard-edged sprite (pixel).
const Cutout = ({ src, t, i, tall }: { src: string; t: Theme; i: number; tall: boolean }) => {
  const f = useF(t)
  const { fps, height, width } = useVideoConfig()
  const s = spring({ frame: f - 4, fps, config: { damping: t.style === '2d' ? 8 : 12 } })
  const box = tall ? { width: width * 0.62, height: height * 0.3 } : { width: width * 0.32, height: height * 0.58 }
  const look = {
    pixel: { padding: 0, background: 'transparent', boxShadow: `8px 8px 0 ${t.accent}`, borderRadius: 0, border: 'none' },
    '2d': { padding: 0, background: 'transparent', boxShadow: `14px 14px 0 ${t.ink[0]}`, borderRadius: 28, border: `8px solid ${t.ink[0]}` },
    editorial: { padding: 16, background: '#fff', boxShadow: '14px 16px 0 rgba(0,0,0,.22)', borderRadius: 0, border: 'none' },
    '3d': { padding: 16, background: '#fff', boxShadow: '14px 16px 0 rgba(0,0,0,.22)', borderRadius: 0, border: 'none' },
  }[t.style]
  return (
    <div style={{ flex: '0 0 auto', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
      <div style={{ position: 'relative', overflow: 'hidden', ...look, transform: `rotate(${(i % 2 ? 3 : -3) * s}deg) scale(${0.7 + 0.3 * s})`, opacity: Math.min(1, s * 1.5) }}>
        <Img src={src} style={{ display: 'block', ...box, objectFit: 'cover', imageRendering: t.step > 1 ? 'pixelated' : 'auto' }} />
      </div>
      {(t.style === 'editorial' || t.style === '3d') && (
        <div style={{ position: 'absolute', width: 150, height: 38, background: 'rgba(240,226,180,.85)', transform: `translateY(${-box.height / 2 - 20}px) rotate(-4deg)`, opacity: s }} />
      )}
    </div>
  )
}

// 2D style: big flat shapes that pop in with squash-and-stretch and float, seeded per segment.
const Shapes2D = ({ t, i }: { t: Theme; i: number }) => {
  const f = useCurrentFrame()
  const { fps, width, height } = useVideoConfig()
  const colors = [t.accent, ...t.bg.filter((_, k) => k !== i % t.bg.length)]
  return (
    <AbsoluteFill style={{ overflow: 'hidden' }}>
      {[0, 1, 2, 3].map((k) => {
        const seed = `${i}-${k}`
        const s = spring({ frame: f - k * 4, fps, config: { damping: 8 } })
        const size = (0.18 + random(`s${seed}`) * 0.22) * Math.max(width, height)
        const x = (k % 2 ? 0.82 : -0.08) * width + random(`x${seed}`) * width * 0.15
        const y = (k < 2 ? -0.06 : 0.72) * height + random(`y${seed}`) * height * 0.15
        const float = Math.sin((f + k * 30) / 28) * 14
        const shape = ['50%', '28%', '50% 50% 8px 50%', '12px'][k]
        return (
          <div key={k} style={{
            position: 'absolute', left: x, top: y + float, width: size, height: size, borderRadius: shape,
            background: colors[(k + 1) % colors.length], opacity: 0.9,
            transform: `scale(${s * (1 + (1 - s) * 0.25)}, ${s * (1 - (1 - s) * 0.25)}) rotate(${(f + k * 50) * (k % 2 ? 0.2 : -0.2)}deg)`,
          }} />
        )
      })}
    </AbsoluteFill>
  )
}

// Reel-style captions: 3-word chunks, the spoken word lit in the accent colour.
const Captions = ({ words, t, tall }: { words: Word[]; t: Theme; tall: boolean }) => {
  const f = useCurrentFrame()
  const { fps } = useVideoConfig()
  const now = f / fps
  const i = words.findIndex((w) => now < w.end)
  if (i < 0 || now < words[0].start) return null
  const chunk = Math.floor(i / 3) * 3
  return (
    <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: 'center', paddingBottom: tall ? '14%' : '6%', pointerEvents: 'none' }}>
      <div style={{ display: 'flex', gap: '0.3em', fontFamily: stack(t.display), fontWeight: 800, fontSize: tall ? 64 : 56, textTransform: 'uppercase', background: 'rgba(0,0,0,.72)', color: '#fff', padding: '10px 22px', borderRadius: 14 }}>
        {words.slice(chunk, chunk + 3).map((w, k) => (
          <span key={k} style={{ color: chunk + k === i && now >= w.start ? t.accent : '#fff' }}>{w.text}</span>
        ))}
      </div>
    </AbsoluteFill>
  )
}

const SceneBody = ({ s, t, ink }: { s: SceneData; t: Theme; ink: string }) => {
  const f = useF(t)
  const { fps } = useVideoConfig()
  const px = t.step > 1
  if (s.kind === 'stat') {
    const n = parseFloat(s.value.replace(/[^\d.]/g, '')) || 0
    const p = interpolate(f, [4, 34], [0, 1], { extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic) })
    const shown = s.value.replace(/[\d.,]+/, (n * p).toFixed(s.value.includes('.') ? 1 : 0))
    return (
      <>
        <div style={{ fontFamily: stack(t.display), fontWeight: 800, fontSize: px ? 150 : 300, color: t.accent, lineHeight: 1 }}>{shown}</div>
        <Words text={s.headline} t={t} size={px ? 34 : 72} color={ink} fx={s.effects} delay={20} />
        <Sub text={s.sub} t={t} color={ink} delay={34} />
      </>
    )
  }
  if (s.kind === 'quote') {
    return (
      <>
        <div style={{ fontFamily: stack(t.display), fontSize: 220, color: t.accent, lineHeight: 0.6, transform: `scale(${spring({ frame: f, fps })})` }}>“</div>
        <Words text={s.headline} t={t} size={px ? 40 : 88} color={ink} fx={s.effects} mark />
        <Sub text={s.sub ? `— ${s.sub}` : ''} t={t} color={ink} delay={26} />
      </>
    )
  }
  const big = s.kind === 'title' || s.kind === 'outro'
  return (
    <>
      {big && <div style={{ height: 14, width: interpolate(f, [0, 14], [0, 220], { extrapolateRight: 'clamp' }), background: t.accent, marginBottom: 40 }} />}
      <Words text={s.headline} t={t} size={(big ? 140 : 100) / (px ? 2.2 : 1)} color={ink} fx={s.effects} />
      <Sub text={s.sub} t={t} color={ink} delay={14} />
    </>
  )
}

const Shot = ({ s, t, i, len, captions }: { s: SceneData; t: Theme; i: number; len: number; captions: boolean }) => {
  const f = useCurrentFrame()
  const { width, height } = useVideoConfig()
  const tall = height >= width
  const fx = s.effects
  const inP = interpolate(f, [0, OVERLAP], [0, 1], { extrapolateRight: 'clamp', easing: Easing.out(Easing.exp) })
  const x = s.transition === 'whip' ? (1 - inP) * width : 0
  const y = s.transition === 'slide' ? (1 - inP) * height : 0
  const blur = s.transition === 'whip' ? (1 - inP) * 40 : 0
  const zoom = s.transition === 'zoom' ? 1 + (1 - inP) * 0.6 : 1
  const flash = s.transition === 'flash' ? interpolate(f, [0, 8], [1, 0], { extrapolateRight: 'clamp' }) : 0
  // Handheld drift: slow push + tiny rotation, different per shot. Punch = stronger push.
  const drift = interpolate(f, [0, len], [1, fx.includes('punch') ? 1.2 : 1.06])
  const rot = Math.sin((f + i * 40) / 45) * 0.4
  // Shake: decaying jitter in the first ~half second.
  const amp = fx.includes('shake') ? interpolate(f, [OVERLAP, OVERLAP + 18], [26, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }) : 0
  const sx = (random(`x${i}-${f}`) - 0.5) * amp
  const sy = (random(`y${i}-${f}`) - 0.5) * amp
  let bg = t.bg[i % t.bg.length]
  let ink = t.ink[i % t.ink.length]
  if (fx.includes('invert')) [bg, ink] = [ink, bg]
  const prop = t.style === '3d' && s.prop ? s.prop : null
  // A 3D prop owns the lower (tall) or right (wide) part of the frame, so the text column narrows and the image cutout steps aside.
  const pad = tall ? `${height * 0.1}px ${width * 0.08}px` : `0 ${width * 0.08}px`
  return (
    <AbsoluteFill style={{ background: bg, transform: `translate(${x + sx}px, ${y + sy}px) scale(${zoom})`, filter: `blur(${blur}px)` }}>
      {t.style === '2d' && <Shapes2D t={t} i={i} />}
      {prop && <Stage3D recipe={prop} len={len} i={i} />}
      <AbsoluteFill style={{
        padding: pad, gap: 70,
        flexDirection: tall ? 'column' : 'row', alignItems: tall ? 'stretch' : 'center',
        justifyContent: prop ? (tall ? 'flex-start' : 'flex-start') : 'center',
        transform: `scale(${drift}) rotate(${rot}deg)`,
      }}>
        {s.asset && tall && !prop && <Cutout src={s.asset} t={t} i={i} tall />}
        <div style={{ flex: tall ? '0 1 auto' : prop ? '0 1 50%' : 1, minWidth: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center', height: !tall && prop ? '100%' : undefined, zoom: prop ? 0.68 : 1 }}>
          <SceneBody s={s} t={t} ink={ink} />
        </div>
        {s.asset && !tall && !prop && <Cutout src={s.asset} t={t} i={i} tall={false} />}
      </AbsoluteFill>
      {fx.includes('vignette') && <AbsoluteFill style={{ background: 'radial-gradient(ellipse at center, transparent 45%, rgba(0,0,0,.55) 100%)' }} />}
      {flash > 0 && <AbsoluteFill style={{ background: '#fff', opacity: flash }} />}
      {s.audio?.url && <Audio src={s.audio.url} />}
      {captions && s.words?.length ? <Captions words={s.words} t={t} tall={tall} /> : null}
    </AbsoluteFill>
  )
}

const Grain = ({ t }: { t: Theme }) => {
  const f = useCurrentFrame()
  if (t.style === 'pixel') return <AbsoluteFill style={{ background: 'repeating-linear-gradient(0deg, rgba(0,0,0,.25) 0 2px, transparent 2px 6px)', pointerEvents: 'none' }} />
  if (!t.grain) return null
  return (
    <AbsoluteFill style={{ opacity: t.grain, mixBlendMode: 'multiply', pointerEvents: 'none' }}>
      <svg width="100%" height="100%">
        <filter id="g"><feTurbulence type="fractalNoise" baseFrequency="0.9" seed={f % 8} /></filter>
        <rect width="100%" height="100%" filter="url(#g)" />
      </svg>
    </AbsoluteFill>
  )
}

export const Main = (p: Plan) => {
  const t = resolveTheme(p.style, p.theme)
  const starts = sceneStarts(p)
  return (
    <AbsoluteFill style={{ background: '#000' }}>
      <style>{fontCss(t)}</style>
      {p.scenes.map((s, i) => {
        const len = sceneLen(s, p.pace)
        return (
          <Sequence key={s.id ?? i} from={starts[i]} durationInFrames={len}>
            <Shot s={{ ...s, effects: s.effects ?? [] }} t={t} i={i} len={len} captions={p.captions !== false} />
          </Sequence>
        )
      })}
      <Grain t={t} />
    </AbsoluteFill>
  )
}
