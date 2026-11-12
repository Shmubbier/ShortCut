# HyperFrames workflow study — 2026-11-12

## Preliminary finding

HyperFrames is a credible renderer/authoring candidate and a promising agent-assisted workflow. The available project documentation does **not** justify replacing Remotion in Blockcut yet. Recommendation: keep the production renderer unchanged and run the disposable parity comparison specified in `briefs/hyperframes-study.md` before deciding.

## What the primary source confirms

- HyperFrames describes an open-source, Apache-2.0 framework that turns HTML, CSS, media and seekable animations into deterministic MP4s. Its CLI previews and renders locally; the documented prerequisites are Node.js 22+ and FFmpeg. The renderer seeks frames in headless Chrome and encodes with FFmpeg. ([Repository README](https://github.com/heygen-com/hyperframes#readme))
- The authoring model uses HTML and timing attributes, with animation adapters for GSAP, CSS, Lottie, Three.js, Anime.js, WAAPI, or custom runtimes. The README lists a catalog containing 3D and camera-move blocks. This makes Three.js integration plausible, but it does not establish that Blockcut's current GLB stage, lighting, camera, and automated scene assignments work unchanged. ([How it works and catalog](https://github.com/heygen-com/hyperframes#how-it-works))
- It has an agent-facing CLI and skills for timeline edits, preview/render and asset workflows. The repository separately describes Studio as “evolving.” Its skill list includes 3D explainer styles and a `remotion-to-hyperframes` migration flow; that flow is a migration aid, not evidence of drop-in parity. Some listed workflows/features are Pro or Studio-specific. ([Skills and stack](https://github.com/heygen-com/hyperframes#quick-start), [Remotion migration skill](https://github.com/heygen-com/hyperframes/tree/main/skills/remotion-to-hyperframes))
- The README says HyperFrames and Remotion both render with headless Chrome and FFmpeg, but use different authoring models (HTML versus React). It notes local/AWS rendering for HyperFrames and mature Lambda rendering for Remotion. ([Comparison](https://github.com/heygen-com/hyperframes#hyperframes-vs-remotion))

## Fit against Blockcut

| Blockcut need | HyperFrames evidence | What remains unverified |
|---|---|---|
| Timeline and media clips | HTML elements can have start, duration, and track attributes; video/audio are shown in README examples. | Mapping all `Plan` tracks, trimming semantics, overlapping transitions and our editor controls. |
| Captions, titles and transitions | Catalog/skills cover captions, overlays, kinetic type and transitions. | Equivalent styling, word timings, exact preview/export behavior. |
| 3D props | Three.js adapter support and catalog entries labeled 3D. | `Stage3D.tsx`/GLB parity, deterministic frame seeking, local asset loading, Windows rendering. |
| Agent workflow | CLI and published skills target coding agents; repository supports Codex and Claude workflows. | Whether skills help maintain Blockcut's product code versus author individual HTML projects; Claude-limit fallback should remain Codex-compatible. |
| Editing UI | README identifies Studio as an evolving browser composition editor. | Whether it can replace Blockcut's custom prompt, inspector, segment canvas, undo/autosave and Plan model. |
| Local demo rendering | Local CLI, Node 22+, FFmpeg; Apache-2.0 repo license. | Install footprint, speed, render reliability and offline behavior on the demo machine. |

## Workflow comparison to run

Use the same frozen Plan and media in both renderers. Select one 9:16 short with two segments, a local video or image, timed captions, narration, music, one transition and one Polyfork GLB. Render a representative still and full MP4, then compare elapsed time, resolution/FPS/audio, frame seeking, 3D loading, output parity and recovery after a missing media file. Keep all HyperFrames code and packages outside the production app until this passes.

## Current limits and next action

This is an official-document/source review, not a HyperFrames install or runtime benchmark. No performance, 3D, or editor replacement claim has been tested locally. Next, run the isolated parity POC from `briefs/hyperframes-study.md`; then record measured findings and decide between a renderer adapter, a focused complementary use, or no adoption.
