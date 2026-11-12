// 3D style: Polyfork GLBs or validated fallback recipes render on a shadow-only floor with an auto-fitted camera.
import { useFrame, useThree } from '@react-three/fiber'
import { ThreeCanvas } from '@remotion/three'
import { useEffect, useMemo, useState } from 'react'
import { continueRender, delayRender, Easing, interpolate, staticFile, useCurrentFrame, useVideoConfig } from 'remotion'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import groundStrip from '../../../bench3d/modelgen/props/ground_strip.json'
import { loadManifold } from './bench3d/manifoldModel'
import { buildRecipe, jointPose, recipeMaterials, type Piece, type Recipe } from './bench3d/recipe'

type V3 = [number, number, number]
type Wasm = Awaited<ReturnType<typeof loadManifold>>
const DEG = Math.PI / 180
const WASM_URL = staticFile('bench3d/manifold.wasm')

export const loadWasm = () => loadManifold(WASM_URL)

export const useManifold = () => {
  const [w, setW] = useState<Wasm>()
  const [handle] = useState(() => delayRender('loading manifold.wasm'))
  useEffect(() => {
    loadWasm().then((x) => { setW(x); continueRender(handle) })
  }, [handle])
  return w
}

// One build per recipe object, shared by preview, thumbnails and the error check on the card.
type Built = { pieces: Piece[]; box: THREE.Box3; error?: undefined } | { error: string; pieces?: undefined; box?: undefined }
const cache = new WeakMap<object, Built>()
export function build(w: Wasm, recipe: Recipe): Built {
  const hit = cache.get(recipe)
  if (hit) return hit
  let out: Built
  try {
    const { pieces } = buildRecipe(w, recipe)
    const box = new THREE.Box3()
    for (const p of pieces) if (p.geo) { p.geo.computeBoundingBox(); box.union(p.geo.boundingBox!) }
    out = { pieces, box }
  } catch (e) {
    out = { error: e instanceof Error ? e.message : String(e) }
  }
  cache.set(recipe, out)
  return out
}

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

// Orbit camera fitted to the prop; view offset pushes the prop away from the text (down in tall frames, right in wide).
const Rig = ({ center, size, follow, len, i }: { center: THREE.Vector3; size: number; follow: V3; len: number; i: number }) => {
  const frame = useCurrentFrame()
  const { width, height } = useVideoConfig()
  const cam = useThree((s) => s.camera) as THREE.PerspectiveCamera
  const dir = i % 2 ? -1 : 1
  const a = interpolate(frame, [0, len], [-28 * dir, 28 * dir], { easing: Easing.inOut(Easing.cubic) }) * DEG
  const tall = height >= width
  const r = size * (tall ? 3.7 : 2.6) + 1.5 // far enough that the whole prop, tall ones included, fits its half of the frame
  const t = center.clone().add(new THREE.Vector3(...follow))
  cam.position.set(t.x + r * Math.sin(a), t.y + size * 0.45, t.z + r * Math.cos(a))
  cam.lookAt(t)
  cam.setViewOffset(width, height, tall ? 0 : -width * 0.22, tall ? -height * 0.2 : 0, width, height)
  cam.updateProjectionMatrix()
  return null
}

const PolyforkCamera = () => {
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera
  const frame = useCurrentFrame()
  const { width, height } = useVideoConfig()
  useFrame(() => {
    camera.position.set(5.8 * Math.sin(frame / 90), 2.6, 8.5 * Math.cos(frame / 90))
    camera.lookAt(0, 1.25, 0)
    camera.aspect = width / height
    camera.updateProjectionMatrix()
  })
  return null
}

const PolyforkStage = ({ model }: { model: { url: string } }) => {
  const { width, height } = useVideoConfig()
  const [handle] = useState(() => delayRender('loading Polyfork GLB'))
  const [loaded, setLoaded] = useState<THREE.Group>()
  useEffect(() => {
    new GLTFLoader().load(model.url.startsWith('/') ? staticFile(model.url.slice(1)) : model.url, (gltf) => {
      const root = gltf.scene.clone(true)
      root.updateMatrixWorld(true)
      const box = new THREE.Box3().setFromObject(root)
      const size = box.getSize(new THREE.Vector3())
      const center = box.getCenter(new THREE.Vector3())
      const scale = 2.6 / Math.max(size.x, size.y, size.z, 0.001)
      root.scale.multiplyScalar(scale)
      root.position.set(-center.x * scale, -center.y * scale + 1.3, -center.z * scale)
      root.traverse((o) => { if ((o as THREE.Mesh).isMesh) { (o as THREE.Mesh).castShadow = true; (o as THREE.Mesh).receiveShadow = true } })
      setLoaded(root)
      continueRender(handle)
    }, undefined, (error) => { console.error('Polyfork GLB failed to load', error); continueRender(handle) })
  }, [handle, model.url])
  return <ThreeCanvas width={width} height={height} shadows={{ type: THREE.PCFSoftShadowMap }} camera={{ fov: 32 }} gl={{ antialias: true, toneMapping: THREE.NoToneMapping }} style={{ position: 'absolute', inset: 0 }}>
    <hemisphereLight args={['#fff8ef', '#d9cbb3', 1.4]} />
    <directionalLight position={[3, 6, 4]} intensity={2.2} castShadow />
    <PolyforkCamera />
    <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow><planeGeometry args={[80, 80]} /><shadowMaterial opacity={0.22} color="#000" transparent /></mesh>
    {loaded && <primitive object={loaded} rotation={[0, -25 * DEG, 0]} />}
  </ThreeCanvas>
}

export const Stage3D = ({ recipe, model, len, i }: { recipe?: Recipe; model?: { url: string }; len: number; i: number }) =>
  model ? <PolyforkStage key={model.url} model={model} /> : recipe ? <RecipeStage3D recipe={recipe} len={len} i={i} /> : null

const RecipeStage3D = ({ recipe, len, i }: { recipe: Recipe; len: number; i: number }) => {
  const w = useManifold()
  const frame = useCurrentFrame()
  const { fps, width, height } = useVideoConfig()
  const built = useMemo(() => (w ? build(w, recipe) : undefined), [w, recipe])
  const travels = !!recipe.motion?.travel
  const ground = useMemo(() => (w && travels ? build(w, groundStrip as unknown as Recipe).pieces?.[0] : undefined), [w, travels])
  const mats = useMemo(() => new Map([...(built?.pieces ?? []), ...(ground ? [{ ...ground, name: '_ground' }] : [])]
    .map((p) => [p.name, recipeMaterials(p.colors)] as const)), [built, ground])
  if (!built?.pieces) return null
  const t = frame / fps
  const offset = (recipe.motion?.travel ?? [0, 0, 0]).map((v) => v * t) as V3
  const size = Math.max(...built.box.getSize(new THREE.Vector3()).toArray(), 0.5)
  const center = built.box.getCenter(new THREE.Vector3())
  const shadowR = size * 1.6
  return (
    <ThreeCanvas width={width} height={height} shadows={{ type: THREE.PCFSoftShadowMap }} camera={{ fov: 32 }}
      gl={{ antialias: true, toneMapping: THREE.NoToneMapping }} style={{ position: 'absolute', inset: 0 }}>
      <Rig center={center} size={size} follow={offset} len={len} i={i} />
      <hemisphereLight args={['#fff8ef', '#d9cbb3', 1.4]} />
      <directionalLight position={[3 + offset[0], 6 + offset[1], 4 + offset[2]]} intensity={2.2} castShadow
        ref={(l) => { if (l) { l.target.position.set(...offset); l.target.updateMatrixWorld() } }}
        shadow-mapSize={[2048, 2048]} shadow-radius={6} shadow-bias={-0.0004}
        shadow-camera-left={-shadowR} shadow-camera-right={shadowR} shadow-camera-top={shadowR} shadow-camera-bottom={-shadowR} />
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[80, 80]} />
        <shadowMaterial opacity={0.22} color="#000" transparent />
      </mesh>
      {ground?.geo && <mesh geometry={ground.geo} material={mats.get('_ground')} castShadow receiveShadow />}
      <group position={offset} rotation={[0, travels ? 0 : -25 * DEG, 0]}>
        <PieceTree pieces={built.pieces} name="root" parentPivot={[0, 0, 0]} t={t} cycle={recipe.motion?.cycle ?? 1} mats={mats} />
      </group>
    </ThreeCanvas>
  )
}
