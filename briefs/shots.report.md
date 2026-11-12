# Shot pipeline report

## Round 2 progress

- Step 1 implementation: six-frame proofs now write `proof.json` and print per-check PASS/FAIL lines for overlap/title-safe zone, floor grounding, paper background Î”E76, and in-frame bounds. Finals require a passing, matching proof; `--force` is the explicit override.
- Proof gate exercise on the unmodified hero: **24/28 checks passed**; four text/object overlap checks failed. Grounding passed on all six frames; background dE76 ranged 1.20â€“1.29; all objects were in frame. A final attempt was correctly blocked (exit 1) before render.
- Step 1 renders/checks took 3.34 s for six proof frames (after scene startup); gate test took 0.76 s. Per-shot corrections and final timings will be added under subsequent step sections.

### Step 2: spec fixes and proof rounds

- **hero-orbit:** 1 spec-tuning proof round after first-pass baseline; **34/34 PASS**, render/check time 3.798 s. The camera target moves the basket into the lower two-thirds; the headline remains in the top third with a clear gap. Basket lowest point is z=0.000 m. Paper sample dE76=0.
- **reveal-rise:** 6 proof rounds; **34/34 PASS**, final check time 3.586 s. Round 1 found title-safe and subject-zone issues. Subsequent camera/title placement fixed these, while scale/framing edits took the orb from 3 in-frame failures to 2, 1, then 0. It enters from below, finishes grounded, and the spec marks the entry airborne/initial off-frame interval as allowed.
- **flyby:** 2 proof rounds; **90/90 PASS**, final check time 6.373 s. Round 1 found the title outside the safe region; moving it down in the spec cleared all checks. All three props have lowest z=0.000 m.
- All proofs used 30 fps, 1920Ã—1080 specs. Refreshed passing contact sheets are in the library README. All background samples are Î”E76â‰¤3 (final successful run: 0.000 for hero/flyby; 0.000 on reveal's final JSON).

### Step 3: app aspect sizes and drafts

- Hero proof rounds for aspect coverage: **2**. First exposed portrait title/object crop and 4:5 title overflow; reducing the hero scale and font size in the spec made 9:16, 16:9, 1:1, and 4:5 all pass **34/34**. Each run rendered six proof frames at 30 fps; check times were approximately 3.6â€“4.1 s.
- Encoded and probed 10-second 30 fps half-resolution MP4s for all four aspect contracts: 540Ã—960 (9:16, 57.89 s), 960Ã—540 (16:9, 51.29 s), 540Ã—540 (1:1, 44.87 s), and 540Ã—674 (4:5, 45.91 s). H.264 4:2:0 requires even dimensions, so the odd 675-pixel 4:5 draft height loses one bottom row during encode. Full-size 1080Ã—1350 remains exact.
- **Required hero final:** 300 frames at 1080Ã—1920 / 30 fps. Blender frame render: **106.82 s**; complete command including startup and H.264 encode: **111.44 s**. Output `shots/out/hero-final-9x16/hero-orbit.mp4`, 670,613 bytes, probed as exactly 10.00 s H.264, 1080Ã—1920, 30 fps.
- A preliminary draft test exposed a double-halving bug and failed 4:5 H.264 encoding. Both were corrected before the successful matrix above: `--draft` now sets Blender's 50% percentage against the full contract dimensions, and encoding trims only the odd 4:5 draft row.
- The final aspect proof pass also required a smaller hero GLB and title to keep both entirely inside 9:16 and 4:5 safe frames. That spec-only follow-up was committed after the step-3 code commit (the first aspect failure exposed the need).

### Step 4: asynchronous API integration

- Added `POST /api/shots/render` and `GET /api/shots/jobs/<id>`. The runner validates a library key or inline JSON spec, starts proof/render work in a daemon job, exposes check details and a proof contact-sheet URL, and refuses finals if checks fail. Completed MP4s are copied to `web/public/footage/` and returned as `/footage/<filename>` for segment use.
- Shared venv server import/AST check passed. Started only the task API at `BLOCKCUT_PORT=8793`; ports 8787, 5173, and 5175 were not touched.
- Proof request (`spec=hero-orbit`, `mode=proof`, `aspect=9:16`) completed with 34/34 checks. Its `proof_url` returned HTTP 200 (317,590 bytes).
- Final request (`spec=hero-orbit`, `mode=final`, `aspect=9:16`) completed after proof and returned `/footage/shot-da0f1cc992f1.mp4` (670,613 bytes). HTTP GET returned 200, `video/mp4`; FFmpeg verified 10.00 s, 1080Ã—1920, 30 fps H.264. The API process on 8793 was stopped after verification.
- Reproduction: run `BLOCKCUT_PORT=8793 .venv/Scripts/python server.py` from the repo root; POST the README sample and poll `/api/shots/jobs/<id>` until `status=completed`. The shared API itself remains untouched.

### Step 5: final audit and commit sequence

- Completed the five steps in order. Round-two commits: `1f20626` proof gate, `2da3a88` spec repairs/proof sheets, `c45b5e3` aspect/draft output, `737f5b0` background API jobs, `18b5737` hero aspect fit; this final audit is the fifth step.
- Final outputs and API-served footage are generated under git-ignored folders. No dependencies were added. The task API on 8793 was shut down after verification; the protected live-test ports were not touched.

## What works

- `shots/render_shot.py` reads the JSON specs, creates EEVEE scenes with GLB props or primitives, animates camera/object keys, draws text overlays, and produces proof records, contact sheets, PNG frames and H.264 MP4s.
- Current library proof results at 30 fps: hero-orbit 34/34, reveal-rise 34/34, flyby 90/90. Contact sheets are embedded in the library README.
- Hero proof checks passed for 9:16, 16:9, 1:1 and 4:5. Draft MP4s were probed at 540×960, 960×540, 540×540 and 540×674; full 4:5 contract output is 1080×1350.
- Current hero final: 10.00 s, 1080×1920, 30 fps H.264, 670,613 bytes; measured 111.44 s end to end. The API final produced the same bytes and returned it from the footage store. The earlier first-pass 24 fps renders are historical outputs and are not the current specs.
- `server.py` and the new `shots.jobs` module import cleanly with the shared venv. `web/out`, `web/public/{footage,renders}` and `shots/out` are git-ignored.

## Known limits

- The EEVEE shadow-catcher floor is soft but subtler than a Cycles shadow. Cycles remains unused due to the known NVIDIA driver failure.
- Encoding calls Remotion's installed FFmpeg binary directly. Its path is resolved from `web/node_modules/@remotion/compositor-win32-x64-msvc/ffmpeg.exe`.
- Proofs sample six evenly spaced frames; a brief event between sample times is not checked by the automated proof.
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

## Verification

- `npx.cmd tsc -b`: passed with no output.
- `node src/video/bench3d/recipe.check.mts`: passed; final line `recipe.ts OK`.
- Shared venv: parsed `server.py`, imported `server`, and printed `server.py AST/import OK`.
- API test at :8793: proof 34/34; final GET from `/footage/` returned 200 and FFmpeg confirmed 10.00 s H.264 1080×1920 at 30 fps.
- All four draft videos and the full hero were probed with Remotion's bundled FFmpeg; aspect, codec, duration and frame rate matched the expected values.

Reproduce the repository checks in PowerShell:

```powershell
cd web
npx.cmd tsc -b
node src/video/bench3d/recipe.check.mts
cd ..
& "C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/.venv/Scripts/python.exe" -c "import ast; ast.parse(open('server.py', encoding='utf-8').read()); import server; print('server.py AST/import OK')"
```
## Dependencies, licensing and merge note

No package was installed or added. Final encoding uses Remotion's already installed FFmpeg binary. Blender and the existing `basket-of-produce-7420cf.glb` are reused from the project; the shot specs and generated compositions are new. No external imagery was downloaded. Merge the `shots/` source files and report; generated renders stay ignored. The destination checkout needs the Blender portable path and normal `web/node_modules` link for renders.
