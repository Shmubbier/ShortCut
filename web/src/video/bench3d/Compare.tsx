// Side-by-side of the three engine renders. Rendered with --public-dir ../bench3d so staticFile reads bench3d/out.
import { AbsoluteFill, Img, OffthreadVideo, staticFile } from 'remotion'

const ENGINES = [
  { label: 'Remotion · @remotion/three', file: 'out/remotion.mp4' },
  { label: 'raea 0.1.1-rc4 · Bevy', file: 'out/raea.mp4' },
  { label: 'Blender 5.3 · EEVEE', file: 'out/blender_eevee.mp4' },
]
export const MODELGEN = [
  { label: 'Manifold (WASM, in browser)', file: 'out/modelgen_manifold.mp4' },
  { label: 'Blender 5.3 → GLB', file: 'out/modelgen_blender.mp4' },
]
const Label = ({ children }: { children: string }) => (
  <div style={{ height: 56, display: 'flex', alignItems: 'center', justifyContent: 'center', font: '600 24px system-ui', color: '#f3ece0', background: '#1d1d1b' }}>{children}</div>
)

// 540 px per engine x 1016: 540x960 tiles under labels
export const Compare = ({ engines = ENGINES }: { engines?: { label: string; file: string }[] }) => (
  <AbsoluteFill style={{ flexDirection: 'row', background: '#1d1d1b' }}>
    {engines.map((e) => (
      <div key={e.file} style={{ width: 540 }}>
        <Label>{e.label}</Label>
        <OffthreadVideo src={staticFile(e.file)} style={{ width: 540, height: 960 }} muted />
      </div>
    ))}
  </AbsoluteFill>
)

// Contact sheet: frames 0 / 60 / 119 per engine, plus the single Blender Cycles (CPU) frame at 60.
const ROWS = [0, 60, 119]
const T = { w: 360, h: 640 }
export const Sheet = () => (
  <AbsoluteFill style={{ background: '#1d1d1b', flexDirection: 'row' }}>
    {[...ENGINES, { label: 'Blender 5.3 · Cycles (CPU)', file: '' }].map((e) => (
      <div key={e.label} style={{ width: T.w }}>
        <Label>{e.label}</Label>
        {ROWS.map((f) => (
          <div key={f} style={{ position: 'relative', width: T.w, height: T.h, borderTop: '2px solid #1d1d1b' }}>
            {e.file ? <OffthreadVideo src={staticFile(e.file)} startFrom={f} style={{ width: T.w, height: T.h }} muted />
              : f === 60 ? <Img src={staticFile('out/blender_cycles_frames/0060.png')} style={{ width: T.w, height: T.h }} />
              : <div style={{ height: '100%', display: 'grid', placeItems: 'center', color: '#8a8478', font: '20px system-ui', textAlign: 'center' }}>not rendered<br />(no GPU backend on<br />driver 566.36)</div>}
            <div style={{ position: 'absolute', right: 8, bottom: 8, font: '600 18px system-ui', color: '#1d1d1b', background: '#f3ece0cc', padding: '2px 8px' }}>f{f}</div>
          </div>
        ))}
      </div>
    ))}
  </AbsoluteFill>
)
