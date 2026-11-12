// Server-side check for AI-written prop recipes (called by server.py `validate_props`).
// stdin: JSON array of recipes (or null for "no prop"); stdout: JSON array of {ok, error?, tris?, ms?}.
// Uses the exact builder the renderer uses, so "ok" here means it will draw in the preview.
import { fileURLToPath } from 'node:url'
import { loadManifold } from './manifoldModel.ts'
import { buildRecipe, type Recipe } from './recipe.ts'

const here = fileURLToPath(new URL('.', import.meta.url))
const w = await loadManifold(here + '../../../node_modules/manifold-3d/manifold.wasm')
let input = ''
for await (const chunk of process.stdin) input += chunk
const recipes = JSON.parse(input) as (Recipe | null)[]
const out = recipes.map((r) => {
  if (!r) return { ok: true, skipped: true }
  try {
    const b = buildRecipe(w, r)
    return { ok: true, tris: b.tris, ms: Math.round(b.ms) }
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) }
  }
})
process.stdout.write(JSON.stringify(out))
