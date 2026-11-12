# Codex task 4: scripted 3D shot pipeline (Blender) + a scene library with exact timings

Branch `codex/shots`. Read `briefs/COMMON.md` first.

## Idea (from the user)
1. Claude directs real apps through scripts. For 3D hero shots, a Python API builds the scene, moves the camera and renders.
   (The user said "reanimate", but that is a Haskell SVG library; **Blender's Python API (bpy)** is the right tool, and
   **Blender 5.3 portable is already installed** at `C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/bench3d/tools/blender-5.3.0-windows-x64/blender.exe`.
   `bench3d/blender/scene.py` already renders a JSON scene headless; reuse what it learned: shadow catcher, text rig, EEVEE settings.)
2. **Start with ONE 10-second shot** before any whole video, and **eliminate render feedback rounds**: precise specs (exact
   timings and easing) instead of "make it look cool", plus a cheap proof render that is checked *before* the expensive final.
3. A **scene library**: finished shots that each ship with the prompt and spec that made them, so the next shot starts from
   a working example (change text, numbers, colours) instead of a blank page.

## Build
1. **Shot spec format** `shots/spec.md` + JSON schema: duration, fps, resolution; camera keyframes `{t, position, look_at, fov,
   easing}` with named easings (`linear, easeInOutCubic, easeOutBack, easeInExpo`… as Bézier handles); objects (GLB path,
   or a prop recipe via the existing Manifold recipe format exported to GLB with three.js `GLTFExporter` from node, or Blender
   primitives); per-object keyframes; lights; background colour (match the paper palette `#f3ece0`); and text overlays with exact in/out times.
2. **`shots/render_shot.py`** (bpy, run with `blender -b --factory-startup -P shots/render_shot.py -- <spec.json> <out> --proof|--final`):
   - **proof:** 6 frames spread over the shot at 25% resolution with EEVEE, low samples, tiled into one contact-sheet PNG
     (with frame times printed), seconds rather than minutes;
   - **final:** a full EEVEE render to PNG frames, then encoded to MP4 with `npx remotion ffmpeg` (in `web/`).
   Report proof and final times. (Cycles GPU fails on this machine's NVIDIA driver 566.36; don't use Cycles.)
3. **The 10-second test shot:** write `shots/library/hero-orbit.json`, a hero product-style shot of a low-poly prop (use
   `bench3d/modelgen/props/boar_rider.json` via GLB export, or a polyfork GLB already in `web/public/bench3d/`). It has a slow
   eased orbit, a push-in at 6 s, a title overlay landing at 1.0 s, and the shadow on paper. Do proof → fix → final, and **count
   the rounds**; the target is one proof round. Save the contact sheet and MP4 under `shots/out/` (git-ignored) and include
   thumbnails in the report.
4. **Scene library:** `shots/library/<name>.json` + `<name>.prompt.md` (the exact prompt that produced the spec) for 3 shots:
   `hero-orbit` (above), `reveal-rise` (object rises into frame with easeOutBack, camera tilt), `flyby` (camera dolly past a row
   of props). Each must render. Add `shots/library/README.md` listing them with thumbnails.
5. **Optional hook (only if 1-4 are done):** `POST /api/shots/render {spec, mode}` as a background job (mirror the existing
   `/api/render` job pattern in `server.py`), so a segment could later use a rendered shot as its footage.

## Done
`hero-orbit` renders in one proof round plus a final MP4, with measured times; the three library shots render; and the report
explains how Claude can write a new spec from a library example.
