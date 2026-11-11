// Remotion CLI entry: npx remotion render src/video/index.tsx Main out/video.mp4 --props=plan.json
import { Composition, registerRoot } from 'remotion'
import { dims, FPS, Main, planDuration, type Plan } from './Video'

const sample: Plan = {
  title: 'Sample', style: 'editorial', pace: 'punchy',
  scenes: [
    { id: 'a', kind: 'title', headline: 'Your hook goes here', sub: '', value: '', transition: 'cut', effects: [] },
    { id: 'b', kind: 'stat', headline: 'a placeholder statistic', sub: 'render with --props=plan.json', value: '42%', transition: 'whip', effects: ['shake'] },
    { id: 'c', kind: 'outro', headline: 'Your payoff here', sub: '', value: '', transition: 'zoom', effects: ['punch'] },
  ],
}

registerRoot(() => (
  <Composition
    id="Main"
    component={Main}
    fps={FPS}
    width={1920}
    height={1080}
    durationInFrames={planDuration(sample)}
    defaultProps={sample}
    calculateMetadata={({ props }) => ({ durationInFrames: planDuration(props), width: dims(props).w, height: dims(props).h })}
  />
))
