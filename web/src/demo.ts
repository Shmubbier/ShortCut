// Demo mode: ready-made videos bundled in /demo (see web/public/demo/index.json) so the editor works with no backend.
import type { Plan } from './video/Video'

export type Mode = 'demo' | 'live'
export type DemoEntry = { file: string; keywords: string[]; title: string }
export type DemoIndex = { plans: DemoEntry[] }

export const DEMO_COOK_MS = 4000 // the cooking screen runs this long so a demo feels like a real generation

let index: Promise<DemoIndex> | null = null
export function loadDemoIndex(): Promise<DemoIndex> {
  if (!index) {
    index = fetch('/demo/index.json').then((r) => { if (!r.ok) throw new Error(`demo index ${r.status}`); return r.json() as Promise<DemoIndex> })
    index.catch(() => { index = null }) // let a failed load retry
  }
  return index
}

export function matchDemo(topic: string, idx: DemoIndex): DemoEntry | null {
  const t = topic.toLowerCase()
  return idx.plans.find((p) => p.keywords.some((k) => t.includes(k.toLowerCase()))) ?? null
}

export async function loadDemoPlan(entry: DemoEntry): Promise<Plan> {
  const r = await fetch(`/demo/${entry.file}`)
  if (!r.ok) throw new Error(`demo video ${r.status}`)
  return r.json()
}
