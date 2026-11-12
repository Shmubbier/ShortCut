Director follow-up (Claude Code). You now have FULL ACCESS: no sandbox, so the shared venv works
(`C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/.venv/Scripts/python`) and `git commit` works. I committed your first pass
and merged the latest `main` (it now has `web/remotion.config.ts`, so `npx remotion ffmpeg` should work again; keep your direct
ffmpeg path as the fallback).

I reviewed `shots/out/hero-orbit/proof.png`. The proof showed real problems, and they went straight to the final render anyway,
which defeats the point: **the proof must catch problems and block the final until they're fixed.**
1. **The title overlaps the basket** in 5 of 6 frames.
2. **The basket floats:** its shadow sits below and beside it, so it doesn't rest on the floor.
3. **The background is grey, not paper `#f3ece0`:** set the view transform to Standard (not AgX/Filmic) and make the world colour
   and floor match exactly. Use a shadow catcher-like floor (the bench3d EEVEE workaround in `bench3d/blender/scene.py`) so the
   frame is paper and the shadow is soft.

Do this:
1. **Automatic proof checks** in `render_shot.py --proof`, printed as PASS/FAIL lines and written to `proof.json`:
   (a) each text overlay's screen box vs each object's projected bounding box at every proof frame: **no overlap**, and text inside
   the title-safe area; (b) each object's lowest point within 1 cm of the floor (y = 0 / z = 0, whichever is up), unless the spec marks
   it `airborne`; (c) the background pixel colour within ΔE ~3 of the spec colour; (d) each object stays fully in frame (unless the
   spec says it enters or exits). `--final` refuses to run if the last proof failed, unless `--force` is passed.
2. **Fix `hero-orbit` with specs alone** (grounding, layout zones: title in the top third, subject in the lower two-thirds) until the proof passes.
   Count proof rounds. Then do the same for `reveal-rise` and `flyby`. Put each passing `proof.png` in the library README.
3. **Real output sizes:** support the app's formats (`9:16` 1080×1920, `16:9` 1920×1080, `1:1`, `4:5`) at **30 fps** (the app's FPS).
   Render hero-orbit final at 1080×1920 and report the time. Keep a `--draft` option (half resolution) for speed.
4. **Connect to the app:** `POST /api/shots/render {spec, mode: proof|final, aspect}` as a background job (mirror the `/api/render`
   job pattern in `server.py`): `GET /api/shots/jobs/<id>` → `{status, stage, proof_url, checks, video_url}`. A finished final is saved
   into the footage store, so it can be dropped on a segment as a video clip (`media: {type: 'video', …}`; this already renders
   in the preview). Test the route on your own API port (8793).
5. Commit in small steps; update the report (rounds, times, check results). Final message as before.
