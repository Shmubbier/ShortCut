// Visual styles, palettes and fonts. A style supplies defaults; the user's theme choices override them.
export type Style = 'editorial' | 'pixel' | '2d' | '3d'
export type ThemeChoice = { palette?: string; accent?: string; display?: string; body?: string; grain?: number }
export type Theme = { bg: string[]; ink: string[]; accent: string; display: string; body: string; grain: number; step: number; style: Style }

export const STYLES: Record<Style, { label: string; palette: string; display: string; body: string; grain: number; step: number }> = {
  editorial: { label: 'Paper editorial', palette: 'paper', display: 'Archivo Black', body: 'Georgia', grain: 0.18, step: 1 },
  pixel: { label: 'Pixel', palette: 'arcade', display: 'Press Start 2P', body: 'Press Start 2P', grain: 0, step: 3 }, // 10fps stepped motion
  '2d': { label: '2D motion', palette: 'pop', display: 'Bricolage Grotesque', body: 'Inter', grain: 0.06, step: 1 },
  '3d': { label: '3D low-poly', palette: 'paper', display: 'Archivo Black', body: 'Georgia', grain: 0.1, step: 1 },
}

// Each palette cycles bg/ink pairs across segments; accent is the highlight colour.
export const PALETTES: Record<string, { label: string; bg: string[]; ink: string[]; accent: string }> = {
  paper: { label: 'Paper', bg: ['#f3ece0', '#1d1d1b', '#e8432e', '#f3ece0', '#2b4bd6'], ink: ['#1d1d1b', '#f3ece0', '#fff8ef', '#1d1d1b', '#fff8ef'], accent: '#e8432e' },
  ube: { label: 'Ube', bg: ['#efe6f7', '#3b1f5c', '#7a4fb3', '#efe6f7', '#f2c14e'], ink: ['#2a1640', '#f3eafc', '#fff', '#2a1640', '#2a1640'], accent: '#7a4fb3' },
  jeepney: { label: 'Jeepney', bg: ['#ffd23f', '#1d3fbb', '#e63946', '#fff4d6', '#0b7a3e'], ink: ['#1b1b1b', '#fff', '#fff', '#1b1b1b', '#fff'], accent: '#e63946' },
  pop: { label: 'Pop', bg: ['#fff3e2', '#ff6b4a', '#2f5bff', '#ffd84d', '#18a874'], ink: ['#1c1c1c', '#fff', '#fff', '#1c1c1c', '#fff'], accent: '#ff6b4a' },
  night: { label: 'Night', bg: ['#121214', '#1f1f24', '#121214', '#2a1d3a', '#121214'], ink: ['#f4f1ea', '#f4f1ea', '#f4f1ea', '#f4f1ea', '#f4f1ea'], accent: '#ff5a36' },
  arcade: { label: 'Arcade', bg: ['#1a1c2c', '#5d275d', '#29366f', '#1a1c2c', '#257179'], ink: ['#f4f4f4', '#ffcd75', '#f4f4f4', '#73eff7', '#f4f4f4'], accent: '#ef7d57' },
  mono: { label: 'Mono', bg: ['#f4f4f2', '#111', '#f4f4f2', '#111', '#dcdcd8'], ink: ['#111', '#f4f4f2', '#111', '#f4f4f2', '#111'], accent: '#111' },
}

// Google Fonts that render reliably in headless Chrome. Georgia is a system font.
export const FONTS = [
  'Archivo Black', 'Anton', 'Bebas Neue', 'Bricolage Grotesque', 'DM Serif Display', 'Fraunces', 'Instrument Serif',
  'Inter', 'Press Start 2P', 'Rubik Mono One', 'Space Grotesk', 'Georgia',
]

const VARIABLE = new Set(['Bricolage Grotesque', 'Fraunces', 'Inter', 'Space Grotesk'])

export function resolveTheme(style: Style | undefined, t: ThemeChoice | undefined): Theme {
  const s = STYLES[style ?? 'editorial'] ?? STYLES.editorial
  const p = PALETTES[t?.palette ?? s.palette] ?? PALETTES.paper
  return {
    bg: p.bg, ink: p.ink, accent: t?.accent ?? p.accent,
    display: t?.display ?? s.display, body: t?.body ?? s.body,
    grain: t?.grain ?? s.grain, step: s.step, style: style ?? 'editorial',
  }
}

export const fontCss = (t: Theme) => {
  const fams = [...new Set([t.display, t.body])].filter((f) => f !== 'Georgia')
  if (!fams.length) return ''
  // Only variable fonts get a weight range; asking a single-weight font for 800 makes the whole request 400.
  const q = fams.map((f) => `family=${f.replace(/ /g, '+')}${VARIABLE.has(f) ? ':wght@400;800' : ''}`).join('&')
  return `@import url('https://fonts.googleapis.com/css2?${q}&display=block');`
}
export const stack = (f: string) => (f === 'Georgia' ? 'Georgia, serif' : `"${f}", system-ui, sans-serif`)
