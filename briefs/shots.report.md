# Shot pipeline report

## Round 2 progress

- Step 1 implementation: six-frame proofs now write `proof.json` and print per-check PASS/FAIL lines for overlap/title-safe zone, floor grounding, paper background ΔE76, and in-frame bounds. Finals require a passing, matching proof; `--force` is the explicit override.
- Proof gate exercise on the unmodified hero: **24/28 checks passed**; four text/object overlap checks failed. Grounding passed on all six frames; background dE76 ranged 1.20–1.29; all objects were in frame. A final attempt was correctly blocked (exit 1) before render.
- Step 1 renders/checks took 3.34 s for six proof frames (after scene startup); gate test took 0.76 s. Per-shot corrections and final timings will be added under subsequent step sections.

### Step 2: spec fixes and proof rounds

- **hero-orbit:** 1 spec-tuning proof round after first-pass baseline; **34/34 PASS**, render/check time 3.798 s. The camera target moves the basket into the lower two-thirds; the headline remains in the top third with a clear gap. Basket lowest point is z=0.000 m. Paper sample dE76=0.
- **reveal-rise:** 6 proof rounds; **34/34 PASS**, final check time 3.586 s. Round 1 found title-safe and subject-zone issues. Subsequent camera/title placement fixed these, while scale/framing edits took the orb from 3 in-frame failures to 2, 1, then 0. It enters from below, finishes grounded, and the spec marks the entry airborne/initial off-frame interval as allowed.
- **flyby:** 2 proof rounds; **90/90 PASS**, final check time 6.373 s. Round 1 found the title outside the safe region; moving it down in the spec cleared all checks. All three props have lowest z=0.000 m.
- All proofs used 30 fps, 1920×1080 specs. Refreshed passing contact sheets are in the library README. All background samples are ΔE76≤3 (final successful run: 0.000 for hero/flyby; 0.000 on reveal's final JSON).

### Step 3: app aspect sizes and drafts

- Hero proof rounds for aspect coverage: **2**. First exposed portrait title/object crop and 4:5 title overflow; reducing the hero scale and font size in the spec made 9:16, 16:9, 1:1, and 4:5 all pass **34/34**. Each run rendered six proof frames at 30 fps; check times were approximately 3.6–4.1 s.
- Encoded and probed 10-second 30 fps half-resolution MP4s for all four aspect contracts: 540×960 (9:16, 57.89 s), 960×540 (16:9, 51.29 s), 540×540 (1:1, 44.87 s), and 540×674 (4:5, 45.91 s). H.264 4:2:0 requires even dimensions, so the odd 675-pixel 4:5 draft height loses one bottom row during encode. Full-size 1080×1350 remains exact.
- **Required hero final:** 300 frames at 1080×1920 / 30 fps. Blender frame render: **106.82 s**; complete command including startup and H.264 encode: **111.44 s**. Output `shots/out/hero-final-9x16/hero-orbit.mp4`, 670,613 bytes, probed as exactly 10.00 s H.264, 1080×1920, 30 fps.
- A preliminary draft test exposed a double-halving bug and failed 4:5 H.264 encoding. Both were corrected before the successful matrix above: `--draft` now sets Blender's 50% percentage against the full contract dimensions, and encoding trims only the odd 4:5 draft row.

## What works

- `shots/render_shot.py` reads the documented JSON spec, builds a Blender EEVEE scene, imports GLB props or creates Blender primitives, animates camera/object keyframes, lights and exact-time text overlays.
- Proof mode rendered six samples of `hero-orbit` at 25% (240×135); Blender reported 4.87 s for the six frame renders. The contact sheet and sample-time list are in `shots/out/hero-orbit/`.
- The final hero is a 10.00 s, 24 fps, 960×540 H.264 MP4 (316,561 bytes). Blender took about 80 s for its 240 final frames (about 0.33 s/frame based on the render log); encoding took a few seconds. It uses the existing basket-of-produce GLB, a slow eased orbit, closer camera keys from 6 s, title visibility starting at 1 s, and a paper floor.
- `reveal-rise` rendered 144 frames and encoded as a 6.00 s, 24 fps H.264 MP4 (119,234 bytes). `flyby` rendered 144 frames in **42.3 s** and encoded as a 6.00 s, 24 fps H.264 MP4 (123,299 bytes). Both are 960×540.
- The library has all three prompts, specs and preview thumbnails. Render output is ignored under `shots/out/`.

## Known limits

- Blender's floor is a regular matte plane; its EEVEE shadow is visible but less subtle than the existing Cycles shadow catcher. Cycles was not used because this machine's NVIDIA driver has the known failure.
- `npx remotion ffmpeg` failed in this worktree because that CLI attempts to bundle a nonexistent `web/remotion.config.ts`. The runner calls the same Remotion package's bundled FFmpeg executable directly; that successfully produced all three H.264 files. If the package path changes, update `ffmpeg` in `render_shot.py`.
- The shared venv Python launcher could not start (`Unable to create process` referring to the Python 3.11 runtime). `server.py` was not changed. The frontend typecheck and prop recipe self-check both passed.
- Proof samples are six uniformly spaced frames; short text events between sample times need visual checking in the final video.

## Reproduce

From the repository root in PowerShell (Blender is already installed at the given absolute path):

```powershell
$blender = "C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/bench3d/tools/blender-5.3.0-windows-x64/blender.exe"
& $blender -b --factory-startup -P shots/render_shot.py -- shots/library/hero-orbit.json shots/out/hero-orbit --proof
& $blender -b --factory-startup -P shots/render_shot.py -- shots/library/hero-orbit.json shots/out/hero-orbit --final
& $blender -b --factory-startup -P shots/render_shot.py -- shots/library/reveal-rise.json shots/out/reveal-rise --final
& $blender -b --factory-startup -P shots/render_shot.py -- shots/library/flyby.json shots/out/flyby --final
```

Each final invocation saves numbered PNGs to `shots/out/<name>/frames/` and writes `shots/out/<name>/<name>.mp4`. Specs and timing/easing vocabulary are described in [shots/spec.md](../shots/spec.md) and [shots/library/README.md](../shots/library/README.md).

Checks run:

```powershell
cd web; npx.cmd tsc -b
node src/video/bench3d/recipe.check.mts
# inspect outputs:
& "C:/Users/naomi/Documents/vscode shenanigans/ManilaHack-wt/shots/web/node_modules/@remotion/compositor-win32-x64-msvc/ffmpeg.exe" -i ../shots/out/hero-orbit/hero-orbit.mp4 -f null NUL
```

All three MP4s were probed with Remotion's bundled FFmpeg and reported the expected duration, H.264, 960×540 and 24 fps. The shared venv `server.py` AST check could not run because its Python launcher could not locate its base Python runtime.

## Dependencies, licensing and merge note

No package was installed or added. Final encoding uses Remotion's already installed FFmpeg binary. Blender and the existing `basket-of-produce-7420cf.glb` are reused from the project; the shot specs and generated compositions are new. No external imagery was downloaded. Merge the `shots/` source files and report; generated renders stay ignored. The destination checkout needs the Blender portable path and normal `web/node_modules` link for renders.
