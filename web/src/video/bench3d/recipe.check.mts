// Self-check for recipe.ts:  node src/video/bench3d/recipe.check.mts   (from web/)
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { loadManifold } from './manifoldModel.ts'
import { buildRecipe, jointPose, RecipeError, type Node } from './recipe.ts'

const here = fileURLToPath(new URL('.', import.meta.url))
const w = await loadManifold(here + '../../../node_modules/manifold-3d/manifold.wasm')
const b = (root: Node, parts?: Record<string, Node>) => {
  const r = buildRecipe(w, { name: 't', root, parts })
  return { ...r, geo: r.pieces[0].geo!, colors: r.pieces[0].colors }
}
const box = (g: ReturnType<typeof b>) => g.geo.boundingBox!

// cylinders and revolves stand along +y, centred / from the profile's heights
assert.ok(Math.abs(box(b({ op: 'cylinder', r: 0.5, h: 2 })).max.y - 1) < 1e-4, 'cylinder is centred on y')
const rev = box(b({ op: 'revolve', profile: [[0, 0], [0.5, 0], [0.2, 1], [0, 1]] }))
assert.ok(Math.abs(rev.max.y - 1) < 1e-4 && Math.abs(rev.min.y) < 1e-4, 'revolve height runs along +y')
// extrude: outline in x-y, thickness along z
assert.ok(Math.abs(box(b({ op: 'extrude', points: [[0, 0], [1, 0], [0, 2]], h: 0.2 })).max.z - 0.1) < 1e-4, 'extrude is centred on z')

// colours survive booleans: the cut face takes the cutter's colour
const cut = b({ op: 'subtract', children: [{ op: 'box', size: [1, 1, 1], color: '#ff0000' }, { op: 'sphere', r: 0.4, at: [0.5, 0.5, 0.5], color: '#00ff00' }] })
assert.deepEqual(cut.colors, ['#ff0000', '#00ff00'])
// colour inherits from the parent; a child's own colour wins
assert.deepEqual(b({ op: 'union', color: '#123456', children: [{ op: 'box', size: [1, 1, 1] }, { op: 'sphere', r: 0.3, at: [2, 0, 0], color: '#abcdef' }] }).colors.sort(), ['#123456', '#abcdef'])

// mirror and array make copies; ref reuses a part
assert.ok(Math.abs(box(b({ op: 'mirror', axis: 'z', children: [{ op: 'sphere', r: 0.1, at: [0, 0, 1] }] })).min.z + 1.1) < 1e-3, 'mirror across z')
assert.ok(Math.abs(box(b({ op: 'array', count: 4, step: [1, 0, 0], children: [{ op: 'box', size: [0.5, 0.5, 0.5] }] })).max.x - 3.25) < 1e-4, 'array steps')
assert.ok(b({ op: 'ref', part: 'leg' }, { leg: { op: 'capsule', r: 0.1, from: [0, 0, 0], to: [0, 1, 0] } }).tris > 0)
// A clockwise outline (the AI's common slip) must not empty the whole union it sits in.
assert.ok(b({ op: 'union', children: [{ op: 'box', size: [1, 1, 1] }, { op: 'extrude', points: [[0, 0.1], [0.08, 0], [0, -0.1], [-0.08, 0]], h: 0.03, at: [2, 0, 0] }] }).tris > 12, 'clockwise extrude')

// bad recipes fail with the path to the bad node, so Claude can fix it
const err = (root: unknown) => assert.throws(() => b(root as Node), RecipeError)
assert.throws(() => b({ op: 'union', children: [{ op: 'box', size: [1, 1, 1] }, { op: 'cone' }] }), /root\.children\[1\]\.op: unknown op "cone"/)
err({ op: 'sphere', r: 1, seg: 1000 }) // over the segment limit
err({ op: 'box', size: [1, 1] })
err({ op: 'box', size: [1, 1, 1], color: 'purple' })
err({ op: 'array', count: 500, children: [{ op: 'box', size: [1, 1, 1] }] })
err({ op: 'ref', part: 'missing' })

// joints split into their own pieces, nest, and are refused where they'd be mirrored or moved by an ancestor
const legs = buildRecipe(w, { name: 'j', root: { op: 'union', children: [
  { op: 'box', size: [1, 0.3, 0.5], at: [0, 1, 0] },
  { op: 'capsule', r: 0.05, from: [0.4, 1, 0], to: [0.4, 0, 0], joint: { name: 'leg', pivot: [0.4, 1, 0], rot: [0, 0, 30] } },
  { op: 'union', joint: { name: 'arm', pivot: [0, 1.2, 0] }, children: [
    { op: 'box', size: [0.1, 0.4, 0.1], at: [0, 1.4, 0] },
    { op: 'sphere', r: 0.1, at: [0, 1.7, 0], joint: { name: 'hand', pivot: [0, 1.6, 0], rot: [10, 0, 0], phase: 0.25 } },
  ] },
] } })
assert.deepEqual(legs.pieces.map((p) => [p.name, p.parent]), [['root', undefined], ['leg', 'root'], ['arm', 'root'], ['hand', 'arm']])
assert.ok(legs.pieces.every((p) => p.geo), 'every piece has geometry')
assert.throws(() => b({ op: 'mirror', axis: 'z', children: [{ op: 'box', size: [1, 1, 1], joint: { name: 'x', pivot: [0, 0, 0] } }] }), /joint can't be inside mirror/)
assert.throws(() => b({ op: 'union', at: [1, 0, 0], children: [{ op: 'box', size: [1, 1, 1], joint: { name: 'x', pivot: [0, 0, 0] } }] }), /joint can't be inside a node with at\/rot\/scale/)
const pose = jointPose({ name: 'leg', pivot: [0, 0, 0], rot: [0, 0, 30] }, 0.25, 1) // a quarter cycle = full swing
assert.ok(Math.abs(pose.rot[2] - Math.PI / 6) < 1e-9)

// the sample props build
for (const f of ['boar_rider', 'hog_rider_fanart']) {
  const r = buildRecipe(w, JSON.parse(readFileSync(here + `../../../../bench3d/modelgen/props/${f}.json`, 'utf8')))
  const colors = new Set(r.pieces.flatMap((p) => p.colors))
  assert.ok(r.tris > 500 && colors.size >= 8, `${f}: ${r.tris} tris, ${colors.size} colours`)
  console.log(`${f}: ${r.nodes} nodes, ${r.pieces.length} pieces, ${r.tris} tris, ${colors.size} colours, ${r.ms.toFixed(1)} ms`)
}
console.log('recipe.ts OK')
