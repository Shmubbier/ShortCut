// Recipe -> three.js geometry with Manifold (WASM). Same shape math as bench3d/modelgen/blender_model.py.
import Module from 'manifold-3d'
import * as THREE from 'three'

export type Recipe = {
  length: number; radius: number; segments: number; taper: number; bend: number
  lumps: { amount: number; seed: number }; skin: string; flesh: string
}
type Wasm = Awaited<ReturnType<typeof Module>>

let wasm: Promise<Wasm> | undefined
export const loadManifold = (wasmUrl: string) =>
  (wasm ??= Module({ locateFile: () => wasmUrl }).then((w) => { w.setup(); return w }))

// unit-sphere vertex -> tuber; deterministic so every engine builds the same shape
export const shape = (r: Recipe, [px, py, pz]: number[]) => {
  const s = r.lumps.seed
  const n = Math.sin(3.1 * px + s) * Math.sin(2.3 * py + 1.7 * s) * Math.sin(2.9 * pz + 2.3 * s)
    + 0.5 * Math.sin(6.1 * px + 0.7 * s) * Math.sin(5.3 * pz + 1.3 * s)
  const k = 1 + r.lumps.amount * n
  const prof = r.radius * (1 - r.taper * px * px) * k
  return [px * (r.length / 2) * (1 + 0.5 * r.lumps.amount * n), py * prof + r.bend * r.radius * (px * px - 0.33), pz * prof]
}

// Geometry group 0 = skin, 1 = flesh (faces made by the cut).
export const buildModel = (w: Wasm, r: Recipe, cut: boolean) => {
  const t0 = performance.now()
  const { Manifold } = w
  const sphere = Manifold.sphere(1, r.segments)
  const tuber = sphere.warp((v) => { const [x, y, z] = shape(r, v); v[0] = x; v[1] = y; v[2] = z }).asOriginal()
  const box = Manifold.cube([4, 4, 4], true).translate([0, 2, 0]).asOriginal() // removes y > 0: the halved ube
  const fleshId = box.originalID()
  const result = cut ? tuber.subtract(box) : tuber
  const mesh = result.getMesh()
  const pos: number[] = []
  const geo = new THREE.BufferGeometry()
  const runs = mesh.runIndex ?? Uint32Array.of(0, mesh.triVerts.length)
  for (let i = 0; i + 1 < runs.length; i++) {
    const start = pos.length / 3
    for (let t = runs[i]; t < runs[i + 1]; t++) {
      const v = mesh.triVerts[t] * mesh.numProp
      pos.push(mesh.vertProperties[v], mesh.vertProperties[v + 1], mesh.vertProperties[v + 2])
    }
    geo.addGroup(start, pos.length / 3 - start, mesh.runOriginalID?.[i] === fleshId ? 1 : 0)
  }
  for (const m of new Set([sphere, tuber, box, result])) m.delete()
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3))
  geo.computeVertexNormals() // non-indexed -> flat, faceted low-poly shading
  return { geo, ms: performance.now() - t0, tris: pos.length / 9 }
}
