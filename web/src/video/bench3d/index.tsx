// Separate entry so the bake-off never touches the main composition:
// npx remotion render src/video/bench3d/index.tsx Bench3D ../bench3d/out/remotion.mp4 --gl=angle
import { Composition, registerRoot } from 'remotion'
import { Bench3D, spec } from './Bench3D'
import { Compare, MODELGEN, Sheet } from './Compare'
import { HOG_RIDER, ModelgenBlender, ModelgenManifold, PropRider } from './ModelGen'

// Compare/Sheet: npx remotion render src/video/bench3d/index.tsx Compare ../bench3d/out/compare.mp4 --public-dir ../bench3d
registerRoot(() => (
  <>
    <Composition id="Bench3D" component={Bench3D} fps={spec.fps} width={spec.width} height={spec.height} durationInFrames={spec.frames} />
    <Composition id="Compare" component={Compare} fps={spec.fps} width={1620} height={1016} durationInFrames={spec.frames} />
    <Composition id="ModelgenManifold" component={ModelgenManifold} fps={spec.fps} width={spec.width} height={spec.height} durationInFrames={spec.frames} />
    <Composition id="ModelgenBlender" component={ModelgenBlender} fps={spec.fps} width={spec.width} height={spec.height} durationInFrames={spec.frames} />
    <Composition id="ModelgenCompare" component={Compare} defaultProps={{ engines: MODELGEN }} fps={spec.fps} width={1080} height={1016} durationInFrames={spec.frames} />
    <Composition id="PropRider" component={PropRider} fps={spec.fps} width={spec.width} height={spec.height} durationInFrames={spec.frames} />
    <Composition id="PropHogRider" component={PropRider} defaultProps={{ recipe: HOG_RIDER }} fps={spec.fps} width={spec.width} height={spec.height} durationInFrames={spec.frames} />
    <Composition id="Sheet" component={Sheet} fps={spec.fps} width={1440} height={56 + 3 * 642} durationInFrames={1} />
  </>
))
