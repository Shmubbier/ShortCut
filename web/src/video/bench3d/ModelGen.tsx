// Generated-model test: the same recipe (bench3d/modelgen/ube.json) built by Manifold live vs by Blender (GLB).
import { useEffect, useMemo, useState } from 'react'
import { continueRender, delayRender, staticFile, useCurrentFrame, useVideoConfig } from 'remotion'
import * as THREE from 'three'
import gen from '../../../../bench3d/modelgen/ube.json'
import { Model, Stage } from './Bench3D'
import { buildModel, loadManifold } from './manifoldModel'
import rider from '../../../../bench3d/modelgen/props/boar_rider.json'
import hogRider from '../../../../bench3d/modelgen/props/hog_rider_fanart.json'
export const HOG_RIDER = hogRider as unknown as Recipe
import groundStrip from '../../../../bench3d/modelgen/props/ground_strip.json'
import { buildRecipe, jointPose, recipeMaterials, type Piece, type Recipe } from './recipe'

const DEG = Math.PI / 180
type Wasm = Awaited<ReturnType<typeof loadManifold>>

const useManifold = () => {
  const [w, setW] = useState<Wasm>()
  const [handle] = useState(() => delayRender('loading manifold.wasm'))
  useEffect(() => { loadManifold(staticFile('bench3d/manifold.wasm')).then((x) => { setW(x); continueRender(handle) }) }, [handle])
  return w
}

export const ModelgenManifold = () => {
  const w = useManifold()
  const built = useMemo(() => w && gen.instances.map((i) => ({ ...i, ...buildModel(w, gen.model, i.cut) })), [w])
  const mats = useMemo(() => [gen.model.skin, gen.model.flesh].map((c) => new THREE.MeshStandardMaterial({ color: c, roughness: 0.8, flatShading: true, shadowSide: THREE.FrontSide })), [])
  const ms = built?.reduce((t, b) => t + b.ms, 0) ?? 0
  return (
    <Stage camera={gen.camera} kicker={`Manifold · ${built?.reduce((t, b) => t + b.tris, 0) ?? 0} tris · built in ${ms.toFixed(1)} ms`}>
      {built?.map((b) => (
        <mesh key={b.name} geometry={b.geo} material={mats} position={b.position as [number, number, number]} rotation={[0, b.rotationY * DEG, 0]} castShadow receiveShadow />
      ))}
    </Stage>
  )
}

export const ModelgenBlender = () => (
  <Stage camera={gen.camera} kicker="Blender 5.3 · headless script → GLB">
    {gen.instances.map((i) => <Model key={i.name} file={`gen/${i.name}.glb`} position={i.position} rotationY={i.rotationY} scale={1} />)}
  </Stage>
)

// A prop recipe (bench3d/modelgen/props/*.json, vocabulary in VOCAB.md) built live with Manifold.
// Joints animate from recipe.motion (frame-driven, so renders are deterministic); a travelling prop gets a
// ground strip and a camera + key light that follow it.
const PROP_CAMERA = { target: [0.15, 1.9, 0], radius: 9.4, height: 2.6, fovY: 32, orbitFromDeg: -55, orbitToDeg: 55, easing: 'inOutCubic' }
type V3 = [number, number, number]

const PieceTree = ({ pieces, name, parentPivot, t, cycle, mats }: {
  pieces: Piece[]; name: string; parentPivot: V3; t: number; cycle: number; mats: Map<string, THREE.Material[]>
}) => {
  const p = pieces.find((x) => x.name === name)!
  const pose = jointPose(p.motion, t, cycle)
  return (
    <group position={[p.pivot[0] - parentPivot[0] + pose.at[0], p.pivot[1] - parentPivot[1] + pose.at[1], p.pivot[2] - parentPivot[2] + pose.at[2]]} rotation={pose.rot}>
      {p.geo && <mesh geometry={p.geo} material={mats.get(p.name)} position={[-p.pivot[0], -p.pivot[1], -p.pivot[2]]} castShadow receiveShadow />}
      {pieces.filter((c) => c.parent === name).map((c) => <PieceTree key={c.name} pieces={pieces} name={c.name} parentPivot={p.pivot} t={t} cycle={cycle} mats={mats} />)}
    </group>
  )
}

export const PropRider = ({ recipe = rider as unknown as Recipe }: { recipe?: Recipe }) => {
  const w = useManifold()
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const t = frame / fps
  const built = useMemo(() => w && buildRecipe(w, recipe), [w, recipe])
  const travels = !!recipe.motion?.travel
  const ground = useMemo(() => w && travels ? buildRecipe(w, groundStrip as unknown as Recipe).pieces[0] : undefined, [w, travels])
  const mats = useMemo(() => new Map([...(built?.pieces ?? []), ...(ground ? [{ ...ground, name: '_ground' }] : [])]
    .map((p) => [p.name, recipeMaterials(p.colors)] as const)), [built, ground])
  const offset = (recipe.motion?.travel ?? [0, 0, 0]).map((v) => v * t) as V3
  return (
    <Stage camera={PROP_CAMERA} title={recipe.title ?? recipe.name} follow={offset}
      kicker={recipe.credit ?? (built ? `${recipe.name} · ${built.nodes} nodes · ${built.tris} tris · ${built.ms.toFixed(0)} ms` : '')}>
      {ground?.geo && <mesh geometry={ground.geo} material={mats.get('_ground')} castShadow receiveShadow />}
      {built && (
        <group position={offset} rotation={[0, travels ? 0 : -30 * DEG, 0]}>
          <PieceTree pieces={built.pieces} name="root" parentPivot={[0, 0, 0]} t={t} cycle={recipe.motion?.cycle ?? 1} mats={mats} />
        </group>
      )}
    </Stage>
  )
}
