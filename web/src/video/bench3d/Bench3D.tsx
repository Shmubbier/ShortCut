// 3D bake-off scene for Remotion (@remotion/three). Spec shared with Blender/raea: bench3d/scene.json.
import { useGLTF } from '@react-three/drei'
import { useThree } from '@react-three/fiber'
import { ThreeCanvas } from '@remotion/three'
import { useMemo, type ReactNode } from 'react'
import { AbsoluteFill, Easing, interpolate, staticFile, useCurrentFrame, useVideoConfig } from 'remotion'
import * as THREE from 'three'
import scene from '../../../../bench3d/scene.json'

export const spec = scene
const DEG = Math.PI / 180

export const Model = ({ file, position, rotationY, scale }: (typeof scene.models)[number]) => {
  const { scene: gltf } = useGLTF(staticFile(`bench3d/${file}`))
  // set shadows at clone time: an effect would run after Remotion already captured the frame
  const obj = useMemo(() => { const o = gltf.clone(); o.traverse((c) => { c.castShadow = c.receiveShadow = true }); return o }, [gltf])
  return <primitive object={obj} position={position} rotation={[0, rotationY * DEG, 0]} scale={scale} />
}

type Cam = typeof scene.camera
type V3 = [number, number, number]
const Rig = ({ c, follow = [0, 0, 0] }: { c: Cam; follow?: V3 }) => {
  const frame = useCurrentFrame()
  const { durationInFrames } = useVideoConfig()
  const a = interpolate(frame, [0, durationInFrames - 1], [c.orbitFromDeg, c.orbitToDeg], { easing: Easing.inOut(Easing.cubic) }) * DEG
  const cam = useThree((s) => s.camera)
  const t = new THREE.Vector3(...c.target).add(new THREE.Vector3(...follow))
  cam.position.set(t.x + c.radius * Math.sin(a), c.height + follow[1], t.z + c.radius * Math.cos(a))
  cam.lookAt(t)
  return null
}

// Paper stage shared by every bench3d composition: orbit camera, key light, shadow-only floor, editorial title.
// follow: shift camera + key light by this much (to track a prop that travels)
export const Stage = ({ camera = scene.camera, kicker = scene.kicker, title = scene.title, follow = [0, 0, 0], children }: { camera?: Cam; kicker?: string; title?: string; follow?: V3; children: ReactNode }) => {
  const [lx, ly, lz] = scene.keyLight.position
  const { width, height } = useVideoConfig()
  return (
    <AbsoluteFill style={{ background: scene.background }}>
      <style>{`@font-face { font-family: "Archivo Black"; src: url(${staticFile(`bench3d/${scene.font}`)}); }`}</style>
      <ThreeCanvas width={width} height={height} shadows={{ type: THREE.PCFSoftShadowMap }} camera={{ fov: camera.fovY }}
        gl={{ antialias: true, toneMapping: THREE.NoToneMapping }}>
        <Rig c={camera} follow={follow} />
        <hemisphereLight args={['#fff8ef', '#d9cbb3', 1.4]} />
        <directionalLight position={[lx + follow[0], ly + follow[1], lz + follow[2]]} intensity={2.2} castShadow
          // the shadow map only covers ±3 m around the target, so the target follows too (inline ref: runs every frame)
          ref={(l) => { if (l) { l.target.position.set(...follow); l.target.updateMatrixWorld() } }}
          shadow-mapSize={[2048, 2048]} shadow-radius={6} shadow-bias={-0.0004}
          shadow-camera-left={-3} shadow-camera-right={3} shadow-camera-top={3} shadow-camera-bottom={-3} />
        <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
          <planeGeometry args={[40, 40]} />
          {/* shadow-only ground so the paper background stays exactly scene.background */}
          <shadowMaterial opacity={scene.shadowOpacity} color={scene.ink} transparent />
        </mesh>
        {children}
      </ThreeCanvas>
      <AbsoluteFill style={{ padding: '170px 80px', fontFamily: '"Archivo Black", sans-serif', color: scene.ink }}>
        <div style={{ fontFamily: 'Georgia, serif', fontStyle: 'italic', fontSize: 40 }}>{kicker}</div>
        <div style={{ fontSize: 168, lineHeight: 0.9, letterSpacing: -6, color: scene.accent, marginTop: 24 }}>
          {title.split(' ').map((w) => <div key={w}>{w}</div>)}
        </div>
        <div style={{ height: 10, width: 260, background: scene.ink, marginTop: 28 }} />
      </AbsoluteFill>
    </AbsoluteFill>
  )
}

export const Bench3D = () => <Stage>{scene.models.map((m) => <Model key={m.file} {...m} />)}</Stage>
