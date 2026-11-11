// raea version of the bake-off scene. Spec shared with Remotion/Blender: ../scene.json
//   raea render bench3d/raea.tsx -o bench3d/out/raea.mp4
import { AbsoluteFill, Composition, Easing, interpolate, registerRoot, staticFile, useCurrentFrame, useVideoConfig } from "raea";
import { Model } from "raea/3d";
import { Camera3d } from "raea/camera";
import { Srgba } from "raea/color";
import { AmbientLight, DirectionalLight } from "raea/light";
import { Mesh3d, Plane3d } from "raea/mesh";
import { StandardMaterial } from "raea/pbr";
import { Transform } from "raea/transform";
import scene from "./scene.json";

const DEG = Math.PI / 180;

function Bench() {
  const f = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const c = scene.camera;
  const a = interpolate(f, [0, durationInFrames - 1], [c.orbitFromDeg, c.orbitToDeg], { easing: Easing.inOut(Easing.cubic), extrapolateLeft: "clamp", extrapolateRight: "clamp" }) * DEG;
  const [tx, ty, tz] = c.target;
  const [lx, ly, lz] = scene.keyLight.position;
  return (
    <AbsoluteFill style={{ background: scene.background }}>
      <style>{`@font-face { font-family: "Archivo Black"; src: url(${staticFile(scene.font)}); }`}</style>
      <Camera3d transform={Transform.fromXyz(tx + c.radius * Math.sin(a), c.height, tz + c.radius * Math.cos(a)).lookingAt([tx, ty, tz])}
        projection={{ Perspective: { fov: c.fovY * DEG } }} />
      <AmbientLight brightness={600} />
      <DirectionalLight transform={Transform.fromXyz(lx, ly, lz).lookingAt([0, 0, 0])} illuminance={9000} shadow_maps_enabled soft_shadow_size={6} />
      {/* shadow-only floor: the page's paper color shows through */}
      <Mesh3d shadow="catch">
        <Plane3d normal={[0, 1, 0]} half_size={[20, 20]} />
        <StandardMaterial base_color={Srgba.hex(scene.ink + Math.round(scene.shadowOpacity * 255).toString(16).padStart(2, "0"))} alpha_mode="Blend" />
      </Mesh3d>
      {scene.models.map((m) => (
        <Model key={m.file} src={staticFile(m.file)} position={m.position as [number, number, number]} rotation={[0, m.rotationY * DEG, 0]} scale={m.scale} />
      ))}
      <div style={{ position: "absolute", left: 80, top: 170, right: 80, color: scene.ink, fontFamily: "Archivo Black" }}>
        <div style={{ fontFamily: "Georgia", fontStyle: "italic", fontSize: 40 }}>{scene.kicker}</div>
        <div style={{ fontSize: 168, lineHeight: 0.9, letterSpacing: -6, color: scene.accent, marginTop: 24 }}>
          {scene.title.split(" ").map((w) => <div key={w}>{w}</div>)}
        </div>
        <div style={{ height: 10, width: 260, background: scene.ink, marginTop: 28 }} />
      </div>
    </AbsoluteFill>
  );
}

registerRoot(() => <Composition id="bench" component={Bench} width={scene.width} height={scene.height} fps={scene.fps} durationInFrames={scene.frames} />);
