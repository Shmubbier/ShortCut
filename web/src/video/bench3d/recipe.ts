// Prop recipes: a JSON node tree (written by Claude) -> three.js geometry, built with Manifold.
// Nodes marked with `joint` become separate pieces that move (legs, arms, a tail), nested like a skeleton.
// Vocabulary + examples for the prompt: bench3d/modelgen/VOCAB.md. Units: meters, y up, degrees, seconds.
import type Module from 'manifold-3d'
import * as THREE from 'three'

type Wasm = Awaited<ReturnType<typeof Module>>
type M = InstanceType<Wasm['Manifold']>
type V3 = [number, number, number]

// A looping motion: offset = amplitude * sin(2π (speed * t / cycle + phase)).
export type Joint = { name: string; pivot: V3; rot?: V3; at?: V3; phase?: number; speed?: number }
export type Node = {
  op: string
  // placement + paint (any node): scale, then rotate (XYZ degrees), then move; colour is inherited by children
  at?: V3; rot?: V3; scale?: number | V3; color?: string
  joint?: Joint
  // primitives
  size?: V3; r?: number; r2?: number; h?: number; seg?: number; from?: V3; to?: V3
  profile?: [number, number][]; points?: [number, number][]
  // operations
  children?: Node[]; axis?: 'x' | 'y' | 'z'; count?: number; step?: V3; stepRot?: V3
  amount?: number; seed?: number; part?: string
}
export type Recipe = {
  name: string; title?: string; credit?: string
  motion?: { cycle: number; travel?: V3 } // cycle: seconds per loop; travel: metres per second the whole prop moves
  parts?: Record<string, Node>; root: Node
}
export type Piece = { name: string; parent?: string; pivot: V3; motion?: Joint; geo?: THREE.BufferGeometry; colors: string[] }

// Limits keep a bad or hostile recipe from hanging the editor.
const MAX = { nodes: 600, seg: 64, count: 32, depth: 24, size: 50, joints: 40 }
const PRIMS = ['box', 'sphere', 'cylinder', 'capsule', 'revolve', 'extrude']
const OPS = ['union', 'subtract', 'intersect', 'hull', 'mirror', 'array', 'warp', 'ref']

export class RecipeError extends Error {}

export function buildRecipe(w: Wasm, recipe: Recipe) {
  const t0 = performance.now()
  const { Manifold } = w
  const made: M[] = [] // every wasm object, freed at the end
  const keep = (m: M) => (made.push(m), m)
  const colorOf = new Map<number, string>() // Manifold originalID -> colour
  let nodes = 0

  const fail = (path: string, msg: string): never => { throw new RecipeError(`${path}: ${msg}`) }
  const num = (path: string, v: unknown, lo: number, hi: number, dflt?: number) => {
    if (v === undefined && dflt !== undefined) return dflt
    if (typeof v !== 'number' || !Number.isFinite(v) || v < lo || v > hi) fail(path, `must be a number in [${lo}, ${hi}], got ${JSON.stringify(v)}`)
    return v as number
  }
  const vec = (path: string, v: unknown, lo = -MAX.size, hi = MAX.size): V3 => {
    if (!Array.isArray(v) || v.length !== 3) fail(path, `must be [x, y, z], got ${JSON.stringify(v)}`)
    return (v as unknown[]).map((x, i) => num(`${path}[${i}]`, x, lo, hi)) as V3
  }
  const poly = (path: string, v: unknown) => {
    if (!Array.isArray(v) || v.length < 3 || v.length > 200) fail(path, 'must be a list of 3-200 [x, y] points')
    return (v as unknown[]).map((p, i) => {
      if (!Array.isArray(p) || p.length !== 2) fail(`${path}[${i}]`, 'must be [x, y]')
      return [num(`${path}[${i}][0]`, (p as number[])[0], -MAX.size, MAX.size), num(`${path}[${i}][1]`, (p as number[])[1], -MAX.size, MAX.size)] as [number, number]
    })
  }
  const paint = (m: M, color: string) => { const o = keep(m.asOriginal()); colorOf.set(o.originalID(), color); return o }
  const yUp = (m: M) => keep(m.rotate([-90, 0, 0])) // Manifold builds cylinders/revolves along z; recipes use y

  // Pieces: the static root plus one per joint. Geometry stays in rest-pose world coordinates; the pivot is where it turns.
  const pieces: (Omit<Piece, 'geo' | 'colors'> & { m?: M })[] = [{ name: 'root', pivot: [0, 0, 0] }]
  const joint = (path: string, j: unknown, parent: string): Joint => {
    if (!j || typeof j !== 'object') fail(path, 'must be an object')
    const o = j as Record<string, unknown>
    const name = typeof o.name === 'string' && /^\w{1,32}$/.test(o.name) ? o.name : fail(`${path}.name`, 'must be 1-32 letters, digits or _')
    if (pieces.some((p) => p.name === name)) fail(`${path}.name`, `joint ${JSON.stringify(name)} already exists`)
    if (pieces.length > MAX.joints) fail(path, `more than ${MAX.joints} joints`)
    const out: Joint = { name, pivot: vec(`${path}.pivot`, o.pivot), phase: num(`${path}.phase`, o.phase, -10, 10, 0), speed: num(`${path}.speed`, o.speed, 0.1, 8, 1) }
    if (o.rot !== undefined) out.rot = vec(`${path}.rot`, o.rot, -180, 180)
    if (o.at !== undefined) out.at = vec(`${path}.at`, o.at, -5, 5)
    pieces.push({ name, parent, pivot: out.pivot, motion: out })
    return out
  }

  // ctx.piece: which piece geometry goes into. ctx.locked: a joint here would be wrong (its geometry would be
  // mirrored, merged or moved by an ancestor), so it's refused with a message saying why.
  type Ctx = { piece: string; locked?: string }
  const build = (n: Node, path: string, inherited: string, depth: number, ctx: Ctx): M | null => {
    if (++nodes > MAX.nodes) fail(path, `recipe has more than ${MAX.nodes} nodes`)
    if (depth > MAX.depth) fail(path, `nested deeper than ${MAX.depth}`)
    if (!n || typeof n !== 'object') fail(path, 'must be an object')
    if (n.joint !== undefined) {
      if (ctx.locked) fail(`${path}.joint`, `a joint can't be inside ${ctx.locked}; put it in a plain union (no at/rot/scale) or another joint`)
      const j = joint(`${path}.joint`, n.joint, ctx.piece)
      const m = build({ ...n, joint: undefined }, path, inherited, depth, { piece: j.name })
      pieces.find((p) => p.name === j.name)!.m = m ?? undefined
      return null // it lives in its own piece
    }
    const color = n.color === undefined ? inherited : /^#[0-9a-fA-F]{6}$/.test(n.color) ? n.color : fail(`${path}.color`, 'must be "#rrggbb"')
    const seg = Math.round(num(`${path}.seg`, n.seg, 3, MAX.seg, 20))
    const moved = n.at !== undefined || n.rot !== undefined || n.scale !== undefined
    const kids = (min: number, locked?: string) => {
      if (!Array.isArray(n.children) || n.children.length < min) fail(`${path}.children`, `${n.op} needs at least ${min} child node(s)`)
      const lock = ctx.locked ?? locked ?? (moved ? `a node with at/rot/scale (${path})` : undefined)
      return n.children!.map((c, i) => build(c, `${path}.children[${i}]`, color, depth + 1, { piece: ctx.piece, locked: lock }))
    }
    const solid = (ms: (M | null)[]) => ms.map((m, i) => m ?? fail(`${path}.children[${i}]`, `${n.op} needs solid children, not only joints`))
    let m: M | null
    switch (n.op) {
      case 'box': m = paint(keep(Manifold.cube(vec(`${path}.size`, n.size, 0.001), true)), color); break
      case 'sphere': m = paint(keep(Manifold.sphere(num(`${path}.r`, n.r, 0.001, MAX.size), seg)), color); break
      case 'cylinder': { // along y, centred; r2 = top radius (0 makes a cone)
        const r = num(`${path}.r`, n.r, 0.001, MAX.size)
        m = paint(yUp(keep(Manifold.cylinder(num(`${path}.h`, n.h, 0.001, MAX.size), r, num(`${path}.r2`, n.r2, 0, MAX.size, r), seg, true))), color)
        break
      }
      case 'capsule': { // rounded limb from -> to
        const r = num(`${path}.r`, n.r, 0.001, MAX.size)
        const a = keep(Manifold.sphere(r, seg).translate(vec(`${path}.from`, n.from))), b = keep(Manifold.sphere(r, seg).translate(vec(`${path}.to`, n.to)))
        m = paint(keep(Manifold.hull([a, b])), color)
        break
      }
      case 'revolve': // profile = [radius, height] points, spun around y
        m = paint(yUp(keep(Manifold.revolve([poly(`${path}.profile`, n.profile)], seg))), color); break
      case 'extrude': // points = outline in the x-y plane, given thickness h along z, centred
        m = paint(keep(Manifold.extrude([poly(`${path}.points`, n.points)], num(`${path}.h`, n.h, 0.001, MAX.size), 0, 0, 1, true)), color); break
      case 'union': { const ms = kids(1).filter((x): x is M => !!x); m = ms.length ? keep(Manifold.union(ms)) : null; break }
      case 'subtract': { const [a, ...rest] = solid(kids(2, 'subtract')); m = keep(Manifold.difference([a, ...rest])); break }
      case 'intersect': m = keep(Manifold.intersection(solid(kids(2, 'intersect')))); break
      case 'hull': m = paint(keep(Manifold.hull(solid(kids(1, 'hull')))), color); break // a hull is one colour
      case 'mirror': { // children plus their mirror image across the plane through the origin facing `axis`
        const u = keep(Manifold.union(solid(kids(1, 'mirror'))))
        const ax = n.axis ?? 'x'
        if (!['x', 'y', 'z'].includes(ax)) fail(`${path}.axis`, 'must be "x", "y" or "z"')
        m = keep(Manifold.union(u, keep(u.mirror(ax === 'x' ? [1, 0, 0] : ax === 'y' ? [0, 1, 0] : [0, 0, 1]))))
        break
      }
      case 'array': { // `count` copies, each moved by `step` and turned by `stepRot` from the previous one
        const u = keep(Manifold.union(solid(kids(1, 'array'))))
        const count = Math.round(num(`${path}.count`, n.count, 1, MAX.count))
        const step = n.step ? vec(`${path}.step`, n.step) : [0, 0, 0], stepRot = n.stepRot ? vec(`${path}.stepRot`, n.stepRot, -360, 360) : [0, 0, 0]
        const copies = Array.from({ length: count }, (_, i) =>
          keep(keep(u.rotate(stepRot.map((d) => d * i) as V3)).translate(step.map((d) => d * i) as V3)))
        m = keep(Manifold.union(copies))
        break
      }
      case 'warp': { // organic lumps: push each vertex along its offset from the part's centre by seeded noise
        const amt = num(`${path}.amount`, n.amount, 0, 0.5), s = num(`${path}.seed`, n.seed, -1e6, 1e6, 1)
        m = keep(keep(Manifold.union(solid(kids(1, 'warp')))).warp((v) => {
          const k = 1 + amt * (Math.sin(3.1 * v[0] / 0.3 + s) * Math.sin(2.3 * v[1] / 0.3 + 1.7 * s) * Math.sin(2.9 * v[2] / 0.3 + 2.3 * s))
          v[0] *= k; v[1] *= k; v[2] *= k
        }))
        break
      }
      case 'ref': { // reuse a named part from recipe.parts
        const p = recipe.parts?.[n.part ?? ''] ?? fail(`${path}.part`, `no part named ${JSON.stringify(n.part)}; have ${Object.keys(recipe.parts ?? {}).join(', ') || 'none'}`)
        m = build(p, `parts.${n.part}`, color, depth + 1, { piece: ctx.piece, locked: ctx.locked ?? (moved ? `a node with at/rot/scale (${path})` : undefined) })
        break
      }
      default: return fail(`${path}.op`, `unknown op ${JSON.stringify(n.op)}; use one of ${[...PRIMS, ...OPS].join(', ')}`)
    }
    if (!m) return null
    if (n.scale !== undefined) m = keep(m.scale(typeof n.scale === 'number' ? num(`${path}.scale`, n.scale, 0.001, MAX.size) : vec(`${path}.scale`, n.scale, 0.001)))
    if (n.rot) m = keep(m.rotate(vec(`${path}.rot`, n.rot, -360, 360)))
    if (n.at) m = keep(m.translate(vec(`${path}.at`, n.at)))
    return m
  }

  const toGeometry = (m: M) => {
    const mesh = m.getMesh()
    const colors: string[] = []
    const pos: number[] = []
    const geo = new THREE.BufferGeometry()
    const runs = mesh.runIndex ?? Uint32Array.of(0, mesh.triVerts.length)
    for (let i = 0; i + 1 < runs.length; i++) {
      const c = colorOf.get(mesh.runOriginalID?.[i] ?? -1) ?? '#9a9a9a'
      if (!colors.includes(c)) colors.push(c)
      const start = pos.length / 3
      for (let t = runs[i]; t < runs[i + 1]; t++) {
        const v = mesh.triVerts[t] * mesh.numProp
        pos.push(mesh.vertProperties[v], mesh.vertProperties[v + 1], mesh.vertProperties[v + 2])
      }
      geo.addGroup(start, pos.length / 3 - start, colors.indexOf(c))
    }
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3))
    geo.computeVertexNormals() // non-indexed -> flat, faceted shading
    geo.computeBoundingBox()
    return { geo, colors }
  }

  try {
    if (recipe.motion !== undefined) {
      num('motion.cycle', recipe.motion?.cycle, 0.05, 60)
      if (recipe.motion.travel !== undefined) vec('motion.travel', recipe.motion.travel, -20, 20)
    }
    pieces[0].m = build(recipe.root, 'root', '#9a9a9a', 0, { piece: 'root' }) ?? undefined
    const out: Piece[] = pieces.map(({ m, ...p }) => (m ? { ...p, ...toGeometry(m) } : { ...p, colors: [] }))
    const tris = out.reduce((t, p) => t + (p.geo ? p.geo.attributes.position.count / 3 : 0), 0)
    return { pieces: out, ms: performance.now() - t0, tris, nodes }
  } finally {
    for (const m of new Set(made)) m.delete()
  }
}

// One material per colour, in geometry-group order. shadowSide FrontSide: these meshes are single-sided.
export const recipeMaterials = (colors: string[]) =>
  colors.map((c) => new THREE.MeshStandardMaterial({ color: c, roughness: 0.85, flatShading: true, shadowSide: THREE.FrontSide }))

// A joint's offset at time t (seconds): rotation in radians and translation, from its looping motion.
export const jointPose = (j: Joint | undefined, t: number, cycle: number) => {
  const s = j ? Math.sin(2 * Math.PI * ((j.speed ?? 1) * t / cycle + (j.phase ?? 0))) : 0
  const DEG = Math.PI / 180
  return {
    rot: (j?.rot ?? [0, 0, 0]).map((d) => d * s * DEG) as V3,
    at: (j?.at ?? [0, 0, 0]).map((d) => d * s) as V3,
  }
}
