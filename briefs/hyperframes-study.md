# Follow-up study: HyperFrames for Blockcut

## Question

Should Blockcut replace Remotion with [HyperFrames](https://github.com/heygen-com/hyperframes), use it alongside Remotion, or keep the current renderer?

## Why it is in the workflow

After the Codex fallback and Polyfork-first 3D path are reviewed, compare HyperFrames against the actual Blockcut workflow before changing render architecture. HyperFrames advertises HTML/CSS compositions, deterministic headless-Chrome/FFmpeg rendering, agent skills, reusable video blocks and an evolving Studio editor. It also publishes a Remotion migration skill. These are useful leads, not proof that it can replace Blockcut's editor or renderer without product work.

## Study workflow

1. **Map requirements.** Trace a real Blockcut Plan through generation, segment editing, preview, 2D/3D/media rendering, captions, voiceover, music, and export. Record which parts are React/Remotion-specific and which are ordinary media or browser animation.
2. **Check fit and constraints.** Verify current HyperFrames CLI/core/Studio maturity, Windows support, Node and FFmpeg requirements, license, offline behavior, seekable Three.js/GLB behavior, audio mixing, clip editing, and local render output. Use official docs and source; distinguish open-source capabilities from Studio or Pro features.
3. **Build a disposable comparison.** In a separate `bench3d/hyperframes-poc/` or temporary directory, reproduce one representative Blockcut segment/short in both renderers: a video/image background, timed narration/captions, music, transition, and a Three.js model. Keep the existing Plan as input and do not change production dependencies or renderer during this step.
4. **Measure and inspect.** Compare setup effort, render time, output dimensions/FPS/audio, deterministic frame seeking, 3D stability, visual parity, asset paths, and failure recovery. Capture exact commands, versions, and output frames.
5. **Recommend.** Choose replace, complement, or retain Remotion. If recommending migration, outline a reversible adapter/dual-renderer path and enumerate editor/UI and Plan-contract changes. No renderer swap based on feature claims alone.

## Decision gates

- Must render the existing Plan's essential timeline and media correctly, including local GLB/Three.js scenes, captions and audio.
- Must run in the team's Windows demo setup and work with the signed-in Codex fallback; no required paid service for local rendering.
- Must provide deterministic frame seeking and a reliable preview/export path.
- Must demonstrate a material improvement in authoring, maintainability, or output quality after accounting for migration cost.

## Deliverables

- `briefs/hyperframes-study.report.md`: dated findings, sources, comparison measurements, representative frames, caveats, and recommendation.
- This brief updated with outcome and any follow-up implementation brief.
